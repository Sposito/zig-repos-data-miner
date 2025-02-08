import pytest
from main import add_commit, add_file, add_folder, add_reference, repo_graph

def test_add_commit():
    add_commit("commit1", "123456", "Alice", "Initial commit")
    assert "commit1" in repo_graph
    assert repo_graph.nodes["commit1"]["node_type"] == "commit"

def test_add_file():
    add_file("file1.zig", "commit1")
    assert "file1.zig" in repo_graph
    assert ("commit1", "file1.zig") in repo_graph.edges

def test_add_folder():
    add_folder("src")
    assert "src" in repo_graph
    assert repo_graph.nodes["src"]["node_type"] == "folder"

def test_add_reference():
    add_reference("file1.zig", "file2.zig")
    assert ("file1.zig", "file2.zig") in repo_graph.edges
