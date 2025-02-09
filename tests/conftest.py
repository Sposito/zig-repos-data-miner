# conftest.py
import pytest
from main import repo_graph


@pytest.fixture
def reset_repo_graph():
    """Reset the global repo_graph before each test."""
    repo_graph.clear()
