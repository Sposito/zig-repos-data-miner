import pytest
import networkx as nx
from unittest.mock import patch, MagicMock, mock_open
from main import process_repository, analyze_zig_file


@pytest.fixture(autouse=True)
def reset_repo_graph():
    global repo_graph
    repo_graph = nx.DiGraph()


@patch("subprocess.run")
@patch("builtins.open", new_callable=mock_open, read_data="const std = @import(\"std\");")
def test_process_repository(mock_file, mock_subprocess):
    global repo_graph
    repo_graph.clear()  # Ensure fresh state before the test

    # Explicitly set stdout to a string
    std_out: str = "commit1|123456|Alice|Initial commit\ncommit2|123457|Bob|Updated"
    mock_subprocess.return_value = MagicMock(stdout=std_out)

    test_graph = nx.DiGraph()  # Create a new test instance

    with patch("os.walk", return_value=[("repo", [], ["main.zig"])]):
        process_repository("repo", graph=test_graph)  # Pass test_graph

    print(f"Graph nodes before assertion: {test_graph.nodes()}")  # Debugging output
    assert "commit1" in test_graph.nodes  # Ensure commit1 exists
    assert "commit2" in test_graph.nodes  # Ensure commit2 exists


def test_analyze_zig_file():
    global repo_graph
    repo_graph.clear()  # Ensure fresh state before the test

    with patch("builtins.open", mock_open(read_data='const std = @import("std");')):
        analyze_zig_file("test.zig", repo_graph)

    print(f"Graph nodes after analyze_zig_file: {repo_graph.nodes()}")
    print(f"Graph edges after analyze_zig_file: {repo_graph.edges()}")
    # Debugging output
    assert "test.zig" in repo_graph.nodes  # Ensure the source file is added
    assert "std" in repo_graph.nodes  # Ensure the imported module is added
    assert ("test.zig", "std") in repo_graph.edges  # Edge should exist
