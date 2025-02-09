
import pytest
from unittest.mock import patch
from main import NodeType
import os
import subprocess
import networkx as nx
from unittest.mock import MagicMock
from main import get_repository_id, process_commits, process_repository, repo_graph


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


# --- Tests for get_repository_id ---
def fake_git_remote_success(args, **kwargs):
    class FakeCompletedProcess:
        def __init__(self, stdout):
            self.stdout = stdout

    # Simulate SSH remote URL response.
    if args[:4] == ["git", "-C", "dummy_repo", "remote"]:
        return FakeCompletedProcess(stdout="git@github.com:user/repo.git")
    raise ValueError("Unexpected command: " + str(args))


def fake_git_remote_https(args, **kwargs):
    class FakeCompletedProcess:
        def __init__(self, stdout):
            self.stdout = stdout

    # Simulate HTTPS remote URL response.
    if args[:4] == ["git", "-C", "dummy_repo", "remote"]:
        return FakeCompletedProcess(stdout="https://github.com/user/repo.git")
    raise ValueError("Unexpected command: " + str(args))


def fake_git_remote_failure(args, **kwargs):
    raise subprocess.CalledProcessError(returncode=1, cmd=args)


def test_get_repository_id_ssh(monkeypatch):
    repo_path = "dummy_repo"
    monkeypatch.setattr(subprocess, "run", fake_git_remote_success)
    repo_id = get_repository_id(repo_path)
    assert repo_id == "user/repo", f"Expected 'user/repo', got {repo_id}"


def test_get_repository_id_https(monkeypatch):
    repo_path = "dummy_repo"
    monkeypatch.setattr(subprocess, "run", fake_git_remote_https)
    repo_id = get_repository_id(repo_path)
    assert repo_id == "user/repo", f"Expected 'user/repo', got {repo_id}"


def test_get_repository_id_failure(monkeypatch):
    repo_path = "dummy_repo"
    monkeypatch.setattr(subprocess, "run", fake_git_remote_failure)
    expected = os.path.basename(os.path.normpath(repo_path))
    repo_id = get_repository_id(repo_path)
    assert repo_id == expected, f"Expected fallback to '{expected}', got {repo_id}"


# --- Tests for process_commits ---

def test_process_commits(monkeypatch):
    repo_path = "dummy_repo"
    repo_id = "dummy_repo"
    fake_git_log = (
        "commit1|1610000000|Alice|Initial commit\n"
        "commit2|1610003600|Bob|Second commit"
    )

    def fake_run(args, **kwargs):
        class FakeCompletedProcess:
            def __init__(self, stdout):
                self.stdout = stdout

        if "log" in args:
            return FakeCompletedProcess(stdout=fake_git_log)
        raise ValueError("Unexpected command: " + str(args))

    monkeypatch.setattr(subprocess, "run", fake_run)
    test_graph = nx.DiGraph()
    process_commits(repo_path, repo_id, test_graph)

    # Verify commit nodes and repository->commit edges.
    for commit in ["commit1", "commit2"]:
        assert commit in test_graph.nodes, f"Commit node '{commit}' not found."
        assert (repo_id, commit) in test_graph.edges, f"Edge from '{repo_id}' to '{commit}' not found."


# --- Tests for process_repository (integration of the new helpers) ---

def test_process_repository(monkeypatch):
    repo_path = "dummy_repo"

    def fake_run(args, **kwargs):
        class FakeCompletedProcess:
            def __init__(self, stdout):
                self.stdout = stdout

        if args[:4] == ["git", "-C", repo_path, "remote"]:
            return FakeCompletedProcess(stdout="git@github.com:user/repo.git")
        elif "log" in args:
            fake_git_log = "commit1|1610000000|Alice|Initial commit"
            return FakeCompletedProcess(stdout=fake_git_log)
        raise ValueError("Unexpected command: " + str(args))

    monkeypatch.setattr(subprocess, "run", fake_run)
    test_graph = nx.DiGraph()
    process_repository(repo_path, graph=test_graph)

    repo_id = "user/repo"  # Extracted from the remote URL
    assert repo_id in test_graph.nodes, "Repository node not found."
    assert "commit1" in test_graph.nodes, "Commit node 'commit1' not found."
    assert (repo_id, "commit1") in test_graph.edges, "Edge from repository to commit not found."
