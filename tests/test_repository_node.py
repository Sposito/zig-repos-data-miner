import pytest
import networkx as nx
from main import add_repository, repo_graph, NodeType

@pytest.fixture(autouse=True)
def reset_repo_graph():
    # Clear the global repo_graph before each test to ensure isolation.
    repo_graph.clear()

def test_add_repository_global_graph():
    """
    Test that add_repository adds a repository node to the global repo_graph.
    """
    repo_id = "repo1"
    add_repository(repo_id)
    assert repo_id in repo_graph
    assert repo_graph.nodes[repo_id]["node_type"] == NodeType.REPOSITORY.value

def test_add_repository_custom_graph():
    """
    Test that add_repository correctly adds a node to a provided graph.
    """
    test_graph = nx.DiGraph()
    repo_id = "custom_repo"
    add_repository(repo_id, graph=test_graph)
    assert repo_id in test_graph
    assert test_graph.nodes[repo_id]["node_type"] == NodeType.REPOSITORY.value
