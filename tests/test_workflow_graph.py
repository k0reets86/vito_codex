from modules.workflow_graph import WorkflowGraph


def test_workflow_graph_validate_and_traverse():
    g = WorkflowGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge("a", "b")
    assert g.validate()
    assert g.next_nodes("a") == ["b"]
    order = g.traverse("a")
    assert order[0] == "a"
    assert "b" in order


def test_workflow_graph_missing_start():
    g = WorkflowGraph()
    assert g.traverse("missing") == []
