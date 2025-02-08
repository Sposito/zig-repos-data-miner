import os
import subprocess
import pytest
import networkx as nx
from unittest.mock import patch, MagicMock
from main import process_repository, repo_graph, NodeType


@pytest.fixture(autouse=True)
def reset_repo_graph():
    # Ensure the global repo_graph is cleared before each test
    repo_graph.clear()


@patch("subprocess.run")
def test_process_repository_creates_repo_and_commits(mock_subproc_run):
    # Arrange: simulate git log output with two commit lines.
    fake_git_log = (
        "commit1|123456|Alice|Initial commit\n"
        "commit2|123457|Bob|Updated commit"
    )
    mock_subproc_run.return_value = MagicMock(stdout=fake_git_log)

    # Provide a test repository path.
    # The repository ID is determined by the folder name.
    test_repo_path = "/some/path/myrepo"

    # Act: Process the repository.
    process_repository(test_repo_path)

    # The repository ID should be the base name of the repository path.
    repo_id = os.path.basename(os.path.normpath(test_repo_path))

    # Assert: Check that the repository node exists.
    assert repo_id in repo_graph, f"Repository node '{repo_id}' not found in the graph."
    assert repo_graph.nodes[repo_id]["node_type"] == NodeType.REPOSITORY.value, \
        f"Expected node type 'repository' for '{repo_id}', got {repo_graph.nodes[repo_id]['node_type']}"

    # Assert: Check that commit nodes exist.
    for commit in ["commit1", "commit2"]:
        assert commit in repo_graph, f"Commit node '{commit}' not found in the graph."
        # And check that an edge exists from the repository node to the commit node.
        assert (repo_id, commit) in repo_graph.edges, \
            f"Edge from repository '{repo_id}' to commit '{commit}' not found."
        # Also verify that the edge has the correct relation.
        assert repo_graph[repo_id][commit]["relation"] == "has_commit", \
            f"Edge from '{repo_id}' to '{commit}' does not have relation 'has_commit'."
