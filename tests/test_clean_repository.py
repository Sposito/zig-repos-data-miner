import subprocess
from pathlib import Path
from unittest.mock import patch, call

from main import clean_repository, clean_all_repositories


def test_clean_repository_success(tmp_path: Path):
    # Create a temporary fake repository with a .git directory.
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    with patch("subprocess.run") as mock_run:
        # Simulate successful subprocess calls.
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        clean_repository(str(repo_dir))

        # Expect two calls: one for "reset --hard", one for "clean -fdx".
        expected_calls = [
            call(
                ["git", "-C", str(repo_dir), "reset", "--hard"],
                capture_output=True,
                text=True,
                check=True,
            ),
            call(
                ["git", "-C", str(repo_dir), "clean", "-fdx"],
                capture_output=True,
                text=True,
                check=True,
            ),
        ]
        mock_run.assert_has_calls(expected_calls, any_order=False)
        assert mock_run.call_count == 2


def test_clean_all_repositories(tmp_path: Path):
    # Create two fake repositories with a .git directory.
    repo1 = tmp_path / "repo1"
    repo1.mkdir()
    (repo1 / ".git").mkdir()

    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    (repo2 / ".git").mkdir()

    # Create a non-repository directory.
    non_repo = tmp_path / "non_repo"
    non_repo.mkdir()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        clean_all_repositories(str(tmp_path))

        # Each repository should result in 2 subprocess calls (reset and clean).
        # With two repositories, we expect 4 calls.
        assert mock_run.call_count == 4

        # Optionally, verify that each call uses the correct repository path.
        expected_calls = [
            call(["git", "-C", str(repo1), "reset", "--hard"], capture_output=True, text=True, check=True),
            call(["git", "-C", str(repo1), "clean", "-fdx"], capture_output=True, text=True, check=True),
            call(["git", "-C", str(repo2), "reset", "--hard"], capture_output=True, text=True, check=True),
            call(["git", "-C", str(repo2), "clean", "-fdx"], capture_output=True, text=True, check=True),
        ]
        mock_run.assert_has_calls(expected_calls, any_order=False)


def test_clean_repository_failure(tmp_path: Path, caplog):
    # Create a temporary fake repository with a .git directory.
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    # Simulate a failure in subprocess.run.
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(returncode=1, cmd="git")):
        clean_repository(str(repo_dir))
        assert "Error cleaning repository" in caplog.text
