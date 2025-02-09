import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
from main import (
    process_repository_files,
    analyze_zig_file,
    process_repository,
    repo_graph,
    NodeType
)


# Ensure a clean graph before each test.
@pytest.fixture(autouse=True)
def reset_repo_graph():
    repo_graph.clear()


# =============================================================================
# (a) Unit Test for File-Scanning Helper
# =============================================================================
def test_file_scanning_helper(tmp_path: Path):
    """
    Simulate a directory structure and verify that:
      - Each folder is added as a node with node_type "folder".
      - For each file, a "contains" edge is created from its parent folder.
    """
    # Create a simulated directory structure:
    # tmp_path/
    # ├── folder1/
    # │   ├── file1.txt
    # │   └── file2.zig
    # └── folder2/
    #     └── file3.txt
    folder1 = tmp_path / "folder1"
    folder1.mkdir()
    file1 = folder1 / "file1.txt"
    file1.write_text("Dummy content for file1.")
    file2 = folder1 / "file2.zig"
    file2.write_text("const dummy = 42;")

    folder2 = tmp_path / "folder2"
    folder2.mkdir()
    file3 = folder2 / "file3.txt"
    file3.write_text("Dummy content for file3.")

    # Call the file-scanning helper on the simulated repository (tmp_path)
    process_repository_files(str(tmp_path), repo_graph)

    # Verify that each folder is present as a folder node.
    for folder in [str(tmp_path), str(folder1), str(folder2)]:
        assert folder in repo_graph.nodes, f"Folder node '{folder}' was not added."
        assert repo_graph.nodes[folder]["node_type"] == NodeType.FOLDER.value, (
            f"Node '{folder}' is not of type 'folder'."
        )

    # For each file, verify that the "contains" edge exists from its parent folder.
    for file_path in [str(file1), str(file2), str(file3)]:
        parent_folder = os.path.dirname(file_path)
        assert (parent_folder, file_path) in repo_graph.edges, (
            f"Edge from '{parent_folder}' to file '{file_path}' not found."
        )


# =============================================================================
# (b) Unit Test for Zig File Analysis
# =============================================================================
def test_zig_file_analysis():
    """
    Simulate reading a .zig file with an @import call and verify that:
      - The source Zig file node is added.
      - The imported module node is added.
      - A "references" edge is created from the source file to the imported module.
    """
    # Fake file content with an @import call.
    fake_content = 'const std = @import("moduleX");'

    # Patch the built-in open so that reading "dummy.zig" returns fake_content.
    m = mock_open(read_data=fake_content)
    with patch("builtins.open", m):
        analyze_zig_file("dummy.zig", repo_graph)

    # Verify the source Zig file node.
    assert "dummy.zig" in repo_graph.nodes, "Source Zig file node 'dummy.zig' was not created."
    assert repo_graph.nodes["dummy.zig"]["node_type"] == NodeType.FILE.value, (
        "Source Zig file node does not have node_type 'file'."
    )

    # Verify the imported module node.
    assert "moduleX" in repo_graph.nodes, "Imported module node 'moduleX' was not created."
    assert repo_graph.nodes["moduleX"]["node_type"] == NodeType.FILE.value, (
        "Imported module node does not have node_type 'file'."
    )

    # Verify that a "references" edge exists.
    assert ("dummy.zig", "moduleX") in repo_graph.edges, (
        "Reference edge from 'dummy.zig' to 'moduleX' not found."
    )
    assert repo_graph["dummy.zig"]["moduleX"]["relation"] == "references", (
        "Edge from 'dummy.zig' to 'moduleX' does not have relation 'references'."
    )


# =============================================================================
# (c) Integration Test for process_repository()
# =============================================================================
def test_integration_process_repository(tmp_path: Path, monkeypatch):
    """
    Create a dummy repository structure with a .git folder, dummy commit log, and files.
    Then verify that:
      - Commit nodes (from the git log) are created.
      - File and folder nodes are created according to the directory structure.
      - Edges such as "contains" and "references" (from Zig file analysis) are present.
    """
    # Create a dummy repository directory structure.
    repo_dir = tmp_path / "dummy_repo"
    repo_dir.mkdir()
    # Create a .git directory to simulate a Git repository.
    (repo_dir / ".git").mkdir()

    # Create dummy files:
    # - A Zig file in the root.
    zig_file = repo_dir / "main.zig"
    zig_file.write_text('const std = @import("moduleRoot");')
    # - A non-Zig file in the root.
    txt_file = repo_dir / "readme.txt"
    txt_file.write_text("This is a readme file.")
    # - A subfolder with a Zig file.
    subfolder = repo_dir / "subdir"
    subfolder.mkdir()
    sub_zig = subfolder / "submodule.zig"
    sub_zig.write_text('const foo = @import("moduleSub");')

    # Simulate git log output by patching subprocess.run.
    fake_git_log = (
        "commit1|1610000000|Alice|Initial commit\n"
        "commit2|1610003600|Bob|Second commit"
    )

    def fake_run(args, **kwargs):
        if "log" in args:
            # When git log is called, return fake_git_log.
            return type("FakeProcess", (), {"stdout": fake_git_log})
        elif "remote" in args:
            # For the remote URL command, simulate failure so
            #     that the repo ID falls back to folder name.
            raise subprocess.CalledProcessError(returncode=1, cmd=args)
        return type("FakeProcess", (), {"stdout": ""})

    monkeypatch.setattr("subprocess.run", fake_run)

    # Run process_repository on the dummy repository.
    process_repository(str(repo_dir), repo_graph)

    # -------------------------------------------------------------------------
    # Verify commit nodes and repository linkage.
    # -------------------------------------------------------------------------
    # The fallback repository id is the folder name "dummy_repo".
    repo_id = "dummy_repo"
    assert repo_id in repo_graph.nodes, "Repository node not created."
    for commit in ["commit1", "commit2"]:
        assert commit in repo_graph.nodes, f"Commit node '{commit}' not found."
        assert (repo_id, commit) in repo_graph.edges, (
            f"Edge from repository '{repo_id}' to commit '{commit}' not found."
        )
        assert repo_graph[repo_id][commit]["relation"] == "has_commit", (
            f"Edge from '{repo_id}' to '{commit}' does not have relation 'has_commit'."
        )

    # -------------------------------------------------------------------------
    # Verify file and folder nodes (via file scanning).
    # -------------------------------------------------------------------------
    # Folder nodes: repository root and the subfolder.
    for folder in [str(repo_dir), str(subfolder)]:
        assert folder in repo_graph.nodes, f"Folder node '{folder}' not found."
        assert repo_graph.nodes[folder]["node_type"] == NodeType.FOLDER.value, (
            f"Node '{folder}' is not of type 'folder'."
        )

    # Check that "readme.txt" has a "contains" edge from the repository root.
    readme_path = str(txt_file)
    assert (str(repo_dir), readme_path) in repo_graph.edges, (
        "Edge from repository root to 'readme.txt' not found."
    )

    # -------------------------------------------------------------------------
    # Verify Zig file analysis for main.zig and submodule.zig.
    # -------------------------------------------------------------------------
    main_zig_path = str(zig_file)
    sub_zig_path = str(sub_zig)
    # For main.zig:
    assert main_zig_path in repo_graph.nodes, "Node for 'main.zig' not found."
    assert "moduleRoot" in repo_graph.nodes, "Imported module 'moduleRoot' from main.zig not found."
    assert (main_zig_path, "moduleRoot") in repo_graph.edges, (
        "Edge from 'main.zig' to 'moduleRoot' not found."
    )
    assert repo_graph[main_zig_path]["moduleRoot"]["relation"] == "references", (
        "Edge from 'main.zig' to 'moduleRoot' does not have relation 'references'."
    )
    # For submodule.zig:
    assert sub_zig_path in repo_graph.nodes, "Node for 'submodule.zig' not found."
    assert "moduleSub" in repo_graph.nodes, "Imported module 'moduleSub' from submodule.zig not found."
    assert (sub_zig_path, "moduleSub") in repo_graph.edges, (
        "Edge from 'submodule.zig' to 'moduleSub' not found."
    )
    assert repo_graph[sub_zig_path]["moduleSub"]["relation"] == "references", (
        "Edge from 'submodule.zig' to 'moduleSub' does not have relation 'references'."
    )
