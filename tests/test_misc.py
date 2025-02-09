import logging
import os
import sqlite3
import pytest
import networkx as nx
from unittest.mock import patch, MagicMock
from math import floor
import time
import tempfile

from main import (
    init_db, save_graph_to_db, load_graph_from_db,
    add_file_to_folder, walk_repos, repo_graph, NodeType, get_commits_for_repo
)

t: int = floor(time.time())
test_name: str = f"test_misc_{t:X}"
logging.info(test_name)


@pytest.fixture
def temp_db():
    """Creates a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        test_db_path = temp_file.name

    try:
        yield test_db_path  # Provide the test function with the database path
    finally:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)


@pytest.fixture(autouse=True)
def reset_repo_graph():
    """Clears the global graph before each test."""
    repo_graph.clear()


# =====================================================================
# (1) TEST DATABASE FUNCTIONS
# =====================================================================

def test_init_db(temp_db):
    """Ensure database initializes correctly with the required tables."""
    init_db(temp_db)  # Use temp_db

    conn = sqlite3.connect(temp_db)
    c = conn.cursor()

    # Verify that tables exist
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'")
    assert c.fetchone() is not None, "Table 'nodes' was not created."

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='edges'")
    assert c.fetchone() is not None, "Table 'edges' was not created."

    conn.close()


def test_save_and_load_graph(temp_db, monkeypatch):
    """Ensure nodes and edges are saved and reloaded correctly."""
    # Patch the global db_path in main to use our temporary database.
    monkeypatch.setattr("main.db_path", temp_db)
    init_db(temp_db)

    # Add sample nodes and edges
    repo_graph.add_node("commit1", type=NodeType.COMMIT.value, timestamp="123456", author="Alice",
                          message="Initial commit")
    repo_graph.add_node("file1.zig", type=NodeType.FILE.value)
    repo_graph.add_edge("commit1", "file1.zig", relation="modifies")

    # Save to DB using the patched db_path.
    save_graph_to_db()
    repo_graph.clear()  # Clear in-memory graph to simulate fresh load

    # Load from DB
    load_graph_from_db()

    # Verify data integrity
    assert "commit1" in repo_graph, "Commit node was not reloaded."
    assert "file1.zig" in repo_graph, "File node was not reloaded."
    assert ("commit1", "file1.zig") in repo_graph.edges, "Edge was not reloaded."
    assert repo_graph["commit1"]["file1.zig"]["relation"] == "modifies"


# =====================================================================
# (2) TEST GRAPH MANIPULATION
# =====================================================================

def test_add_file_to_folder():
    """Ensure add_file_to_folder correctly links a file to its parent folder."""
    add_file_to_folder("/repo/src/main.zig")

    assert "/repo/src" in repo_graph, "Parent folder node was not created."
    assert "/repo/src/main.zig" in repo_graph, "File node was not created."
    assert ("/repo/src", "/repo/src/main.zig") in repo_graph.edges, "File-folder relationship was not established."
    assert repo_graph["/repo/src"]["/repo/src/main.zig"]["relation"] == "contains"


# =====================================================================
# (3) TEST REPOSITORY WALKING FUNCTION
# =====================================================================

def test_walk_repos():
    """Ensure walk_repos correctly iterates over repositories and invokes the action function."""
    from unittest.mock import MagicMock
    mock_graph = nx.DiGraph()
    mock_action = MagicMock()

    def fake_exists(path):
        """Mock `os.path.exists()` to return True only for repo1 and repo2."""
        return path in {"/fake/path/repo1/.git", "/fake/path/repo2/.git"}

    from unittest.mock import patch
    with patch("os.listdir", return_value=["repo1", "repo2", "not_a_repo"]), \
         patch("os.path.isdir", return_value=True), \
         patch("os.path.exists", side_effect=fake_exists):
        walk_repos("/fake/path", mock_graph, ".git", mock_action)

    # Debugging: Print how many times mock_action was called and with what arguments
    print(f"mock_action called {mock_action.call_count} times with: {mock_action.call_args_list}")

    # Ensure action function was called for repo1 and repo2, but not for "not_a_repo"
    assert mock_action.call_count == 2, f"Expected 2 calls but got {mock_action.call_count} calls."
    mock_action.assert_any_call("/fake/path/repo1", mock_graph)
    mock_action.assert_any_call("/fake/path/repo2", mock_graph)


# =====================================================================
# (4) TEST GET COMMITS FOR REPO API FUNCTION
# =====================================================================

def test_get_commits_for_repo(temp_db, monkeypatch):
    """
    Test that get_commits_for_repo correctly retrieves commit history from the database.
    """
    # Patch the global db_path in main to use our temporary database.
    monkeypatch.setattr("main.db_path", temp_db)
    init_db(temp_db)

    # Insert sample repository and commit data into the database.
    conn = sqlite3.connect(temp_db)
    c = conn.cursor()
    repo_id = "testuser/testrepo"

    # Insert repository node
    c.execute("INSERT INTO nodes (id, type) VALUES (?, ?)", (repo_id, NodeType.REPOSITORY.value))

    # Insert commit nodes
    commits = [
        ("commit1", NodeType.COMMIT.value, "1610000000", "Alice", "Initial commit"),
        ("commit2", NodeType.COMMIT.value, "1610003600", "Bob", "Second commit"),
    ]
    c.executemany("INSERT INTO nodes (id, type, timestamp, author, message) VALUES (?, ?, ?, ?, ?)", commits)

    # Insert edges linking commits to the repository
    edges = [(repo_id, "commit1", "has_commit"), (repo_id, "commit2", "has_commit")]
    c.executemany("INSERT INTO edges (src, dest, relation) VALUES (?, ?, ?)", edges)

    conn.commit()
    conn.close()

    # Call the function and check the result
    result = get_commits_for_repo(repo_id, temp_db)
    expected = [
        {"commit": "commit1"[:7], "timestamp": "1610000000", "author": "Alice", "message": "Initial commit"},
        {"commit": "commit2"[:7], "timestamp": "1610003600", "author": "Bob", "message": "Second commit"},
    ]
    assert result == expected, f"Expected {expected}, but got {result}"

