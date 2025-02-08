import logging
from fastapi import FastAPI
import networkx as nx
import os
import subprocess
import re
import enum
import uvicorn
import sqlite3
from typing import List, Dict

app = FastAPI()
repo_graph = nx.DiGraph()
repos_path = os.path.expanduser("~/Projects/ProjectsArchive/zig-trainer")
db_path = "./repo_graphs.db"


# --- Enum for Node Types ---
class NodeType(enum.Enum):
    COMMIT = "commit"
    FILE = "file"
    FOLDER = "folder"
    REPOSITORY = "repository"  # New NodeType for repositories


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
    print("Database initialized successfully.")  # Debug log


def save_graph_to_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Store nodes using dictionary format
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

    # Store edges using dictionary format
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
        graph = repo_graph  # Use the global graph if none is provided
    graph.add_node(commit_hash, node_type=NodeType.COMMIT.value, timestamp=timestamp, author=author, message=message)


def add_file(file_path: str, commit_hash: str, prev_commit: str = None):
    global repo_graph
    if file_path not in repo_graph:
        repo_graph.add_node(file_path, node_type=NodeType.FILE.value)
    # Fixed the typo here: removed the erroneous 'cd -'
    repo_graph.add_edge(commit_hash, file_path, relation="modifies")


def add_folder(folder_path: str):
    if folder_path not in repo_graph:
        repo_graph.add_node(folder_path, node_type=NodeType.FOLDER.value)


def add_file_to_folder(file_path: str):
    folder_path = os.path.dirname(file_path)
    add_folder(folder_path)
    repo_graph.add_edge(folder_path, file_path, relation="contains")


def add_reference(src_file: str, dest_file: str):
    global repo_graph
    if src_file not in repo_graph:
        repo_graph.add_node(src_file, node_type=NodeType.FILE.value)
    if dest_file not in repo_graph:
        repo_graph.add_node(dest_file, node_type=NodeType.FILE.value)
    repo_graph.add_edge(src_file, dest_file, relation="references")


def add_repository(repo_id: str, graph=None):
    """
    Adds a repository node to the graph with the given repo_id.
    """
    if graph is None:
        graph = repo_graph
    graph.add_node(repo_id, node_type=NodeType.REPOSITORY.value)


# --- Process Repositories ---
def process_repositories():
    for repo_name in os.listdir(repos_path):
        repo_dir = os.path.join(repos_path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, ".git")):
            process_repository(repo_dir)


def process_repository(repo_path: str, graph=None):
    global repo_graph
    if graph is None:
        graph = repo_graph

    # Determine repository ID by retrieving and parsing the remote URL.
    try:
        remote_result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        remote_url = remote_result.stdout.strip()
        repo_id = None

        if remote_url.startswith("git@"):
            # SSH format, e.g.:
            # "git@github.com:getty-zig/getty.git"
            path_part = remote_url.split(":", 1)[1]
            if path_part.endswith(".git"):
                path_part = path_part[:-4]
            parts = path_part.split("/")
        elif remote_url.startswith("https://"):
            # HTTPS format, e.g.:
            # "https://github.com/getty-zig/getty.git" or "https://github.com/getty-zig/getty"
            parts = remote_url.split("/")
            if parts[-1].endswith(".git"):
                parts[-1] = parts[-1][:-4]
        else:
            parts = []

        if len(parts) >= 2:
            # Assuming the last two parts are the username and repository name.
            repo_id = f"{parts[-2]}/{parts[-1]}"
        else:
            repo_id = os.path.basename(os.path.normpath(repo_path))
    except Exception as e:
        # If any error occurs (e.g., remote URL not available), fallback to the folder name.
        repo_id = os.path.basename(os.path.normpath(repo_path))

    # Add a repository node to the graph with the composite repository ID.
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

            # Add commit node
            add_commit(commit_hash, timestamp, author, message, graph=graph)
            # Add an edge from the repository node to the commit node
            graph.add_edge(repo_id, commit_hash, relation="has_commit")




def analyze_zig_file(file_path: str, graph=repo_graph):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # Extract imports
            imports = set(re.findall(r'@import\s*\(\s*"(.*?)"\s*\)', content))

            for imp in imports:
                graph.add_node(file_path, node_type=NodeType.FILE.value)
                graph.add_node(imp, node_type=NodeType.FILE.value)
                graph.add_edge(file_path, imp, relation="references")

    except Exception as e:
        logging.warning(f"Failed to analyze {file_path}: {e}")


# --- API Endpoints ---
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


# --- Run API Server ---
if __name__ == "__main__":
    init_db()
    load_graph_from_db()
    process_repositories()
    save_graph_to_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
