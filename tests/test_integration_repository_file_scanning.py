import os
from unittest.mock import patch, MagicMock, mock_open
import pytest

from main import process_repository, repo_graph


@pytest.fixture(autouse=True)
def reset_repo_graph():
    repo_graph.clear()


@patch("main.process_repository_files")
@patch("subprocess.run")
def test_process_repository_calls_file_scanning(mock_subproc_run, mock_process_repo_files):
    """
    Verify that process_repository calls process_repository_files after processing commit history.
    """
    # Simulate git log output with one commit.
    fake_git_log = "commit1|123456|Alice|Initial commit"
    mock_subproc_run.return_value = MagicMock(stdout=fake_git_log)

    test_repo_path = "/dummy/path/repo"
    process_repository(test_repo_path)

    # Check that process_repository_files is called with the repository path and the global graph.
    mock_process_repo_files.assert_called_once_with(test_repo_path, repo_graph)


@patch("os.walk")
@patch("subprocess.run")
@patch("builtins.open", new_callable=mock_open, read_data='const std = @import("std");')
def test_process_repository_file_scanning(mock_file, mock_subproc_run, mock_os_walk):
    """
    Simulate a repository with a .zig file and verify that file nodes, folder nodes,
    and import references are added to the graph.
    """
    # Setup a fake os.walk: one directory with one Zig file.
    fake_walk = [
        ("/dummy/path/repo", ["subdir"], ["main.zig"])
    ]
    mock_os_walk.return_value = fake_walk

    # Simulate a git log output with one commit.
    fake_git_log = "commit1|123456|Alice|Initial commit"
    mock_subproc_run.return_value = MagicMock(stdout=fake_git_log)

    test_repo_path = "/dummy/path/repo"
    process_repository(test_repo_path)

    # Verify commit node and repository edge are added.
    repo_id = os.path.basename(os.path.normpath(test_repo_path))
    assert repo_id in repo_graph, f"Repository node '{repo_id}' not found."
    assert "commit1" in repo_graph, "Commit node 'commit1' not found."
    assert (repo_id, "commit1") in repo_graph.edges, "Edge from repository to commit not found."

    # Verify that the file scanning has added the file node.
    main_zig_path = os.path.join("/dummy/path/repo", "main.zig")
    assert main_zig_path in repo_graph.nodes, f"File node '{main_zig_path}' not added to graph."

    # The analyze_zig_file function should have found an import "std".
    assert "std" in repo_graph.nodes, "Imported module node 'std' not added to graph."
    assert (main_zig_path, "std") in repo_graph.edges, (
        f"Reference edge from '{main_zig_path}' to 'std' not found."
    )
