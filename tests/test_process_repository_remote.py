import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from main import process_repository, repo_graph, NodeType


@pytest.fixture(autouse=True)
def reset_repo_graph():
    # Ensure the global repo_graph is cleared before each test.
    repo_graph.clear()


def fake_subprocess_run(args, **kwargs):
    """
    Fake subprocess.run implementation for a successful remote URL retrieval.
    Returns:
      - A remote URL for the "remote get-url origin" command.
      - Fake git log output for the "git log" command.
    """
    if args[0] == "git" and "-C" in args and "remote" in args and "get-url" in args:
        # Simulate a valid remote URL (SSH format)
        return MagicMock(stdout="git@github.com:getty-zig/getty.git")
    elif args[0] == "git" and "-C" in args and "log" in args:
        # Simulate git log output with two commits.
        fake_git_log = (
            "commit1|123456|Alice|Initial commit\n"
            "commit2|123457|Bob|Updated commit"
        )
        return MagicMock(stdout=fake_git_log)
    else:
        raise ValueError("Unexpected command: " + str(args))


@patch("subprocess.run", side_effect=fake_subprocess_run)
def test_process_repository_with_remote_url(mock_subproc_run):
    """
    Test process_repository() when the remote URL is successfully retrieved.
    Expect the repository ID to be extracted from the remote URL (i.e. "getty-zig/getty")
    and commits to be linked to that repository.
    """
    # The repository path can be arbitrary because the remote URL takes precedence.
    test_repo_path = "/some/path/somerepo"
    process_repository(test_repo_path)

    # Expected repository id derived from the remote URL should be "getty-zig/getty".
    repo_id = "getty-zig/getty"

    # Verify repository node exists with the correct node type.
    assert repo_id in repo_graph, f"Repository node '{repo_id}' not found in the graph."
    assert repo_graph.nodes[repo_id]["node_type"] == NodeType.REPOSITORY.value, (
        f"Expected node type 'repository' for '{repo_id}', got {repo_graph.nodes[repo_id]['node_type']}"
    )

    # Verify commit nodes and that each commit is linked with the "has_commit" relation.
    for commit in ["commit1", "commit2"]:
        assert commit in repo_graph, f"Commit node '{commit}' not found in the graph."
        assert (repo_id, commit) in repo_graph.edges, (
            f"Edge from repository '{repo_id}' to commit '{commit}' not found."
        )
        assert repo_graph[repo_id][commit]["relation"] == "has_commit", (
            f"Edge from '{repo_id}' to '{commit}' does not have relation 'has_commit'."
        )


def fake_subprocess_run_fallback(args, **kwargs):
    """
    Fake subprocess.run implementation for when the remote URL lookup fails.
    For the remote command, simulate failure; for git log, return fake output.
    """
    if args[0] == "git" and "-C" in args and "remote" in args and "get-url" in args:
        # Simulate a failure for the remote URL command.
        raise subprocess.CalledProcessError(returncode=1, cmd=args)
    elif args[0] == "git" and "-C" in args and "log" in args:
        fake_git_log = (
            "commit1|123456|Alice|Initial commit\n"
            "commit2|123457|Bob|Updated commit"
        )
        return MagicMock(stdout=fake_git_log)
    else:
        raise ValueError("Unexpected command: " + str(args))


@patch("subprocess.run", side_effect=fake_subprocess_run_fallback)
def test_process_repository_fallback_to_folder_name(mock_subproc_run):
    """
    Test process_repository() when the remote URL lookup fails.
    Expect the repository ID to fallback to the folder name.
    """
    test_repo_path = "/some/path/fallbackrepo"
    process_repository(test_repo_path)

    # Fallback: repository ID should be the folder name ("fallbackrepo").
    repo_id = os.path.basename(os.path.normpath(test_repo_path))

    # Verify repository node exists with the correct node type.
    assert repo_id in repo_graph, f"Repository node '{repo_id}' not found in the graph (fallback)."
    assert repo_graph.nodes[repo_id]["node_type"] == NodeType.REPOSITORY.value, (
        f"Expected node type 'repository' for '{repo_id}', got {repo_graph.nodes[repo_id]['node_type']} (fallback)."
    )

    # Verify commit nodes exist and are linked with the "has_commit" relation.
    for commit in ["commit1", "commit2"]:
        assert commit in repo_graph, f"Commit node '{commit}' not found in the graph (fallback)."
        assert (repo_id, commit) in repo_graph.edges, (
            f"Edge from repository '{repo_id}' to commit '{commit}' not found (fallback)."
        )
        assert repo_graph[repo_id][commit]["relation"] == "has_commit", (
            f"Edge from '{repo_id}' to '{commit}' does not have relation 'has_commit' (fallback)."
        )
