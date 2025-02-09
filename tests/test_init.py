from main import main_entry


def test_main_entry_calls_all_functions(monkeypatch):
    """
    This test verifies that main_entry() calls the expected functions in order:
      - init_db
      - load_graph_from_db
      - clean_all_repositories
      - process_repositories
      - walk_repos
      - save_graph_to_db
      - uvicorn.run
    Each function is monkey-patched with a fake that records its call.
    """

    call_order = []

    def fake_init_db(*args, **kwargs):
        call_order.append("init_db")

    def fake_load_graph_from_db(*args, **kwargs):
        call_order.append("load_graph_from_db")

    def fake_clean_all_repositories(*args, **kwargs):
        call_order.append("clean_all_repositories")

    def fake_process_repositories(*args, **kwargs):
        call_order.append("process_repositories")

    def fake_walk_repos(*args, **kwargs):
        call_order.append("walk_repos")

    def fake_save_graph_to_db(*args, **kwargs):
        call_order.append("save_graph_to_db")

    def fake_uvicorn_run(*args, **kwargs):
        call_order.append("uvicorn_run")

    # Patch the fn in the main module so that their side effects are recorded instead of executed.
    monkeypatch.setattr("main.init_db", fake_init_db)
    monkeypatch.setattr("main.load_graph_from_db", fake_load_graph_from_db)
    monkeypatch.setattr("main.clean_all_repositories", fake_clean_all_repositories)
    monkeypatch.setattr("main.process_repositories", fake_process_repositories)
    monkeypatch.setattr("main.walk_repos", fake_walk_repos)
    monkeypatch.setattr("main.save_graph_to_db", fake_save_graph_to_db)
    monkeypatch.setattr("main.uvicorn.run", fake_uvicorn_run)

    # Call the main entry function.
    main_entry()

    # Verify that the functions were called in the proper order.
    expected_order = [
        "init_db",
        "load_graph_from_db",
        "clean_all_repositories",
        "process_repositories",
        "walk_repos",
        "save_graph_to_db",
        "uvicorn_run"
    ]

    assert call_order == expected_order, f"Expected call order {expected_order}, but got {call_order}"
