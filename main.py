import logging
from fastapi import FastAPI
import networkx as nx
import os
import subprocess
import re
import enum
import uvicorn
import sqlite3
from typing import List, Dict, Callable

app = FastAPI()
repo_graph = nx.DiGraph()
repos_path = os.path.expanduser("~/Projects/ProjectsArchive/zig-trainer")
db_path = "./dbs/repo_graphs.db"
ignore_cleaning = True


# --- Enum for Node Types ---
class NodeType(enum.Enum):
    COMMIT = "commit"
    FILE = "file"
    FOLDER = "folder"
    REPOSITORY = "repository"


# --- SQLite Setup ---
def init_db(path: str = None):
    """
    Initializes the SQLite database by creating required tables if they do not exist.
    """

    if path is None:
        path = db_path
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            type TEXT,
            timestamp TEXT,
            author TEXT,
            message TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            src TEXT,
            dest TEXT,
            relation TEXT,
            PRIMARY KEY (src, dest, relation)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            should_clean BOOLEAN DEFAULT FALSE
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


def save_graph_to_db():
    """
    Saves the current state of the repository graph to the SQLite database.
    Nodes and edges are inserted if they do not already exist.
    """

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    node_data: List[Dict[str, str]] = [
        {
            "id": n,
            "type": str(repo_graph.nodes[n].get("node_type", "")),
            "timestamp": str(repo_graph.nodes[n].get("timestamp", "")),
            "author": str(repo_graph.nodes[n].get("author", "")),
            "message": str(repo_graph.nodes[n].get("message", ""))
        }
        for n in repo_graph.nodes
    ]
    if node_data:
        c.executemany("""
            INSERT OR IGNORE INTO nodes (id, type, timestamp, author, message)
            VALUES (:id, :type, :timestamp, :author, :message)
        """, node_data)

    edge_data: List[Dict[str, str]] = [
        {
            "src": u,
            "dest": v,
            "relation": str(repo_graph[u][v].get("relation", ""))
        }
        for u, v in repo_graph.edges
    ]
    if edge_data:
        c.executemany("""
            INSERT OR IGNORE INTO edges (src, dest, relation)
            VALUES (:src, :dest, :relation)
        """, edge_data)

    conn.commit()
    conn.close()


def load_graph_from_db():
    """
    Loads the repository graph from the SQLite database into memory.
    Nodes and edges are reconstructed in the NetworkX graph.
    """

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("SELECT * FROM nodes")
    for row in c.fetchall():
        node_id, node_type, timestamp, author, message = row
        repo_graph.add_node(node_id,
                            node_type=node_type,
                            timestamp=timestamp,
                            author=author,
                            message=message)

    c.execute("SELECT * FROM edges")
    for row in c.fetchall():
        src, dest, relation = row
        repo_graph.add_edge(src, dest, relation=relation)

    conn.close()


# --- Graph Construction Helpers ---
def add_commit(commit_hash: str, timestamp: str, author: str, message: str, graph=None):
    """
    Adds a commit node to the repository graph.

    Parameters:
    - commit_hash: Unique identifier for the commit.
    - timestamp: Unix timestamp of the commit.
    - author: Author of the commit.
    - message: Commit message.
    - graph: Optional graph instance; defaults to the global repo_graph.
    """
    if graph is None:
        graph = repo_graph
    graph.add_node(commit_hash, node_type=NodeType.COMMIT.value,
                   timestamp=timestamp, author=author, message=message)


def add_file(file_path: str, commit_hash: str, prev_commit: str = None):
    """
    Adds a file node to the repository graph and links it to a commit that modifies it.

    Parameters:
    - file_path: Path to the file.
    - commit_hash: Commit that modified the file.
    - prev_commit: Optional previous commit for tracking file history.
    """

    if file_path not in repo_graph:
        repo_graph.add_node(file_path, node_type=NodeType.FILE.value)
    repo_graph.add_edge(commit_hash, file_path, relation="modifies")


def add_folder(folder_path: str):
    """
    Adds a folder node to the repository graph.

    Parameters:
    - folder_path: Path to the folder.
    """

    if folder_path not in repo_graph:
        repo_graph.add_node(folder_path, node_type=NodeType.FOLDER.value)


def add_file_to_folder(file_path: str):
    """
    Links a file to its containing folder in the graph.

    Assumptions:
    - File paths use POSIX-style separators
    - Parent folder hierarchy already exists or will be created
    """
    folder_path = os.path.dirname(file_path)
    add_folder(folder_path)
    repo_graph.add_edge(folder_path, file_path, relation="contains")


def add_reference(src_file: str, dest_file: str):
    """
    Adds a reference edge between two files, indicating that one references the other.

    Parameters:
    - src_file: The file that contains the reference.
    - dest_file: The file being referenced.
    """

    if src_file not in repo_graph:
        repo_graph.add_node(src_file, node_type=NodeType.FILE.value)
    if dest_file not in repo_graph:
        repo_graph.add_node(dest_file, node_type=NodeType.FILE.value)
    repo_graph.add_edge(src_file, dest_file, relation="references")


def add_repository(repo_id: str, graph=None):
    """
    Adds a repository node to the graph.

    Parameters:
    - repo_id: Unique identifier for the repository.
    - graph: Optional graph instance; defaults to the global repo_graph.
    """

    if graph is None:
        graph = repo_graph
    graph.add_node(repo_id, node_type=NodeType.REPOSITORY.value)


# --- Repository Processing ---
def get_repository_id(repo_path: str) -> str:
    """
    Extracts the repository ID from the remote URL if available,
    otherwise falls back to the repository folder name.
    """
    try:
        remote_result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        remote_url = remote_result.stdout.strip()
        repo_id = None
        if remote_url.startswith("git@"):
            path_part = remote_url.split(":", 1)[1]
            if path_part.endswith(".git"):
                path_part = path_part[:-4]
            parts = path_part.split("/")
        elif remote_url.startswith("https://"):
            parts = remote_url.split("/")
            if parts[-1].endswith(".git"):
                parts[-1] = parts[-1][:-4]
        else:
            parts = []
        if len(parts) >= 2:
            repo_id = f"{parts[-2]}/{parts[-1]}"
        else:
            repo_id = os.path.basename(os.path.normpath(repo_path))
    except Exception:
        repo_id = os.path.basename(os.path.normpath(repo_path))
    return repo_id


def process_commits(repo_path: str, repo_id: str, graph):
    """
    Processes the commit history from the repository and adds commit nodes
    and repository->commit edges to the graph.
    """
    git_log_cmd = ["git", "-C", repo_path, "log", "--pretty=format:%H|%at|%an|%s", "--reverse"]
    try:
        result = subprocess.run(git_log_cmd, capture_output=True, text=True, check=True)
        git_log_output = result.stdout.splitlines()
    except subprocess.CalledProcessError:
        git_log_output = []

    for line in git_log_output:
        commit_data = line.split("|")
        if len(commit_data) == 4:
            commit_hash, timestamp, author, message = commit_data
            add_commit(commit_hash, timestamp, author, message, graph=graph)
            graph.add_edge(repo_id, commit_hash, relation="has_commit")


def process_repository(repo_path: str, graph=None):
    """
    Processes a single repository by extracting its remote information,
    commits, and file structure into the graph.
    """
    if graph is None:
        graph = repo_graph

    repo_id = get_repository_id(repo_path)
    add_repository(repo_id, graph=graph)

    # Process commits before scanning files.
    process_commits(repo_path, repo_id, graph)

    # Process repository files.
    process_repository_files(repo_path, graph)

    # Process commits again.
    process_commits(repo_path, repo_id, graph)


def process_repositories():
    """
    Iterates over all repositories in the configured directory and processes them.
    """
    for repo_name in os.listdir(repos_path):
        repo_dir: str = os.path.join(repos_path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, ".git")):
            process_repository(repo_dir)


def analyze_zig_file(file_path: str, graph=repo_graph):
    """
    Analyzes Zig source files for module dependencies via @import statements.

    Assumptions:
    - Only processes .zig files
    - Uses simple regex pattern matching (not full AST parsing)
    - Imports are assumed to be file-relative paths
    - Files are UTF-8 encoded

    Security Note:
    - File I/O operations should be sandboxed in production
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            imports = set(re.findall(r'@import\s*\(\s*"(.*?)"\s*\)', content))
            for imp in imports:
                graph.add_node(file_path, node_type=NodeType.FILE.value)
                graph.add_node(imp, node_type=NodeType.FILE.value)
                graph.add_edge(file_path, imp, relation="references")
    except Exception as e:
        logging.warning(f"Failed to analyze {file_path}: {e}")


def process_repository_files(repo_path: str, graph):
    """
    Processes all files and folders in a repository, building structural relationships.

    Features:
    - Creates folder nodes for each directory
    - Creates file nodes and 'contains' relationships
    - Analyzes Zig files for cross-module references

    Limitations:
    - Only processes .zig files for code analysis
    - Maximum directory depth is system/file handle limit
    """
    for root, dirs, files in os.walk(repo_path):
        add_folder(root)
        for directory in dirs:
            folder_path = os.path.join(root, directory)
            add_folder(folder_path)
        for file in files:
            file_path = os.path.join(root, file)
            add_file_to_folder(file_path)
            if file.endswith('.zig'):
                analyze_zig_file(file_path, graph)


def walk_repos(path: str, graph, signature: str, action: Callable[[str, any], None]):
    """
    Walks through repositories and executes processing action

    Assumptions:
    - Repositories are direct children of the root path
    - Signature file (typically .git) indicates valid repos
    - Action function handles its own error checking
    """
    for repo_name in os.listdir(path):
        repo_dir = os.path.join(path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, signature)):
            action(repo_dir, graph)


# --- Repository Cleaning ---
def clean_repository(repo_path: str):
    """
    Resets and cleans a Git repository, discarding uncommitted changes.

    Parameters:
    - repo_path: Path to the repository to clean.
    """

    try:
        subprocess.run(["git", "-C", repo_path, "reset", "--hard"],
                       capture_output=True, text=True, check=True)

        subprocess.run(["git", "-C", repo_path, "clean", "-fdx"],
                       capture_output=True, text=True, check=True)
        logging.info(f"Cleaned repository: {repo_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error cleaning repository {repo_path}: {e}")


def clean_all_repositories(path: str, signature: str = ".git", ignore: bool = False):
    """
    Cleans all repositories in the specified directory by resetting and removing untracked files.

    Parameters:
    - path: Root directory containing repositories.
    - signature: File or folder indicating a valid repository (default is ".git").
    """
    if ignore:
        return

    for repo_name in os.listdir(path):
        repo_dir = os.path.join(path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, signature)):
            clean_repository(repo_dir)


# --- API Endpoint ---
@app.get("/repos/{repo_id}/commits")
def get_commits_for_repo(repo_id: str, path: str = None):
    """
    Retrieves commit history for a specific repository from the database.

    Parameters:
    - repo_id: Unique identifier of the repository.

    Returns:
    - A list of commits containing commit hash, timestamp, author, and message.
    """
    if path is None:
        path = db_path

    conn = sqlite3.connect(path)
    c = conn.cursor()
    query = """
    SELECT n.id, n.timestamp, n.author, n.message
    FROM nodes n
    JOIN edges e ON n.id = e.dest
    WHERE e.src = ? AND e.relation = 'has_commit' AND n.type = ?
    """
    c.execute(query, (repo_id, NodeType.COMMIT.value))
    commits = [
        {
            "commit": row[0][:7],
            "timestamp": row[1],
            "author": row[2],
            "message": row[3]
        }
        for row in c.fetchall()
    ]
    conn.close()
    return commits


# --- Main Execution ---


def main_entry():
    init_db()
    load_graph_from_db()

    clean_all_repositories(path=repos_path, ignore=ignore_cleaning)

    process_repositories()

    walk_repos(repos_path, repo_graph, ".git", process_repository_files)
    save_graph_to_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main_entry()
