from fastapi import FastAPI
import networkx as nx
import os
import subprocess
import re
import enum
import sqlite3
import uvicorn

# Initialize API and Graph
app = FastAPI()
repo_graph = nx.DiGraph()
repos_path = "./repos"
db_path = "./repo_graphs.db"


# --- Enum for Node Types ---
class NodeType(enum.Enum):
    COMMIT = "commit"
    FILE = "file"
    FOLDER = "folder"


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


def save_graph_to_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Store nodes
    c.executemany("""
        INSERT OR IGNORE INTO nodes (id, type, timestamp, author, message) 
        VALUES (?, ?, ?, ?, ?)
    """, [(n, repo_graph.nodes[n].get("node_type"),
           repo_graph.nodes[n].get("timestamp"),
           repo_graph.nodes[n].get("author"),
           repo_graph.nodes[n].get("message")) for n in repo_graph.nodes])

    # Store edges
    c.executemany("""
        INSERT OR IGNORE INTO edges (src, dest, relation) 
        VALUES (?, ?, ?)
    """, [(u, v, repo_graph[u][v]["relation"]) for u, v in repo_graph.edges])

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


# --- Process Repositories ---
def process_repositories():
    for repo_name in os.listdir(repos_path):
        repo_dir = os.path.join(repos_path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, ".git")):
            process_repository(repo_dir)


def process_repository(repo_path: str, graph=None):
    global repo_graph
    if graph is None:
        graph = repo_graph  # Use the global graph unless another is provided

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

    except Exception:
        pass


# --- API Endpoints ---
@app.get("/commits")
def get_commits():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, author, message FROM nodes WHERE type = ?", (NodeType.COMMIT.value,))
    commits = [{"commit": row[0][:7], "timestamp": row[1], "author": row[2], "message": row[3]} for row in c.fetchall()]
    conn.close()
    return commits


# --- Run API Server ---
if __name__ == "__main__":
    init_db()
    load_graph_from_db()
    process_repositories()
    save_graph_to_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
