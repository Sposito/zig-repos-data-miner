from fastapi import FastAPI
import networkx as nx
import os
import subprocess
import re
import pandas as pd
from typing import List, Dict, Optional
import uvicorn

# Initialize API and Graph
app = FastAPI()
repo_graph = nx.DiGraph()
repos_path = "./repos"

# --- Graph Construction Helpers ---
def add_commit(commit_hash: str, timestamp: str, author: str, message: str):
    repo_graph.add_node(commit_hash, node_type="commit", timestamp=timestamp, author=author, message=message)

def add_file(file_path: str, commit_hash: str):
    if file_path not in repo_graph:
        repo_graph.add_node(file_path, node_type="file")
    repo_graph.add_edge(commit_hash, file_path, relation="modifies")

def add_reference(src_file: str, dest_file: str):
    if src_file not in repo_graph:
        repo_graph.add_node(src_file, node_type="file")
    if dest_file not in repo_graph:
        repo_graph.add_node(dest_file, node_type="file")
    repo_graph.add_edge(src_file, dest_file, relation="references")

# --- Process Repositories ---
def process_repositories():
    for repo_name in os.listdir(repos_path):
        repo_dir = os.path.join(repos_path, repo_name)
        if os.path.isdir(repo_dir) and os.path.exists(os.path.join(repo_dir, ".git")):
            process_repository(repo_dir)

def process_repository(repo_path: str):
    git_log_cmd = ["git", "-C", repo_path, "log", "--pretty=format:%H|%at|%an|%s", "--reverse"]
    try:
        result = subprocess.run(git_log_cmd, capture_output=True, text=True, check=True)
        git_log_output = result.stdout.splitlines()
    except subprocess.CalledProcessError:
        git_log_output = []

    for line in git_log_output:
        commit_hash, timestamp, author, message = line.split("|", 3)
        add_commit(commit_hash, timestamp, author, message)

    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".zig"):
                full_path = os.path.join(root, file)
                add_file(full_path, commit_hash)
                analyze_zig_file(full_path)

def analyze_zig_file(file_path: str):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            imports = set(re.findall(r'@import\s*\(\s*"(.*?)"\s*\)', content))
            for imp in imports:
                add_reference(file_path, imp)
    except:
        pass


# --- API Endpoints ---
@app.get("/commits")
def get_commits() -> List[Dict]:
    return [repo_graph.nodes[n] for n in repo_graph.nodes if repo_graph.nodes[n].get('node_type') == "commit"]

# --- Run API Server ---
if __name__ == "__main__":
    # Process all repositories at startup
    process_repositories()
    uvicorn.run(app, host="0.0.0.0", port=8000)

