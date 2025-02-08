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
db_path = "./repo_graphs.db"


# --- Enum for Node Types ---
class NodeType(enum.Enum):
    COMMIT = "commit"
    FILE = "file"
    FOLDER = "folder"
    REPOSITORY = "repository"


# --- SQLite Setup ---
def init_db():
    conn = sqlite3.connect(db_path)
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
    conn.commit()
    conn.close()
    print("Database initialized successfully.")


def save_graph_to_db():
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
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("SELECT * FROM nodes")
    for row in c.fetchall():
        node_id, node_type, timestamp, author, message = row
        repo_graph.add_node(node_id, node_type=node_type, timestamp=timestamp, author=author, message=message)

    c.execute("SELECT * FROM edges")
    for row in c.fetchall():
        src, dest, relation = row
        repo_graph.add_edge(src, dest, relation=relation)

    conn.close()


# --- Graph Construction Helpers ---
def add_commit(commit_hash: str, timestamp: str, author: str, message: str, graph=None):
    if graph is None:
        graph = repo_graph
    graph.add_node(commit_hash, node_type=NodeType.COMMIT.value, timestamp=timestamp, author=author, message=message)


def add_file(file_path: str, commit_hash: str, prev_commit: str = None):
    if file_path not in repo_graph:
        repo_graph.add_node(file_path, node_type=NodeType.FILE.value)
    repo_graph.add_edge(commit_hash, file_path, relation="modifies")


def add_folder(folder_path: str):
    if folder_path not in repo_graph:
        repo_graph.add_node(folder_path, node_type=NodeType.FOLDER.value)


def add_file_to_folder(file_path: str):
    folder_path = os.path.dirname(file_path)
    add_folder(folder_path)
    repo_graph.add_edge(folder_path, file_path, relation="contains")


def add_reference(src_file: str, dest_file: str):
    if src_file not in repo_graph:
        repo_graph.add_node(src_file, node_type=NodeType.FILE.value)
    if dest_file not in repo_graph:
        repo_graph.add_node(dest_file, node_type=NodeType.FILE.value)
    repo_graph.add_edge(src_file, dest_file, relation="references")


def add_repository(repo_id: str, graph=None):
    if graph is None:
        graph = repo_graph
    graph.add_node(repo_id, node_type=NodeType.REPOSITORY.value)


# --- Repository Processing ---
def process_repositories():
    for repo_name in os.listdir(repos_path):
        repo_dir = os.path.join(repos_path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, ".git")):
            process_repository(repo_dir)


def process_repository(repo_path: str, graph=None):
    if graph is None:
        graph = repo_graph

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

    add_repository(repo_id, graph=graph)

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


def analyze_zig_file(file_path: str, graph=repo_graph):
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
    for repo_name in os.listdir(path):
        repo_dir = os.path.join(path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, signature)):
            action(repo_dir, graph)


# --- Repository Cleaning ---
def clean_repository(repo_path: str):
    try:
        subprocess.run(["git", "-C", repo_path, "reset", "--hard"], capture_output=True, text=True, check=True)
        subprocess.run(["git", "-C", repo_path, "clean", "-fdx"], capture_output=True, text=True, check=True)
        print(f"Cleaned repository: {repo_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error cleaning repository {repo_path}: {e}")


def clean_all_repositories(path: str, signature: str = ".git"):
    for repo_name in os.listdir(path):
        repo_dir = os.path.join(path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, signature)):
            clean_repository(repo_dir)


# --- API Endpoint ---
@app.get("/repos/{repo_id}/commits")
def get_commits_for_repo(repo_id: str):
    conn = sqlite3.connect(db_path)
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
if __name__ == "__main__":
    init_db()
    load_graph_from_db()

    # Clean all repositories so they return to a clean state.
    clean_all_repositories(repos_path)

    # Process repositories for commit history.
    process_repositories()

    # Process each repository's files and folders.
    walk_repos(repos_path, repo_graph, ".git", process_repository_files)

    save_graph_to_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
