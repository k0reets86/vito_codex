from modules.knowledge_graph import KnowledgeGraph


def test_knowledge_graph_records_knowledge_and_neighbors(tmp_path):
    graph = KnowledgeGraph(str(tmp_path / "kg.db"))
    graph.record_knowledge(
        "doc:test",
        {
            "agent": "ecommerce_agent",
            "platform": "etsy",
            "task_family": "listing_create",
            "skill_name": "etsy_draft_fill",
            "task_root_id": "task-1",
        },
    )
    neighbors = graph.neighbors("doc:test")
    relations = {row["relation"] for row in neighbors}
    assert "mentions_agent" in relations
    assert "mentions_platform" in relations
    assert "mentions_task_family" in relations
    assert "mentions_skill" in relations
    assert "mentions_goal" in relations


def test_knowledge_graph_records_lessons(tmp_path):
    graph = KnowledgeGraph(str(tmp_path / "kg.db"))
    graph.record_lesson(
        "lesson:test",
        goal_id="goal-7",
        task_family="research",
        source_agent="research_agent",
        candidate_skill="trend_loop",
        metadata={"platform": "gumroad"},
    )
    neighbors = graph.neighbors("lesson:test")
    relations = {row["relation"] for row in neighbors}
    assert "belongs_to_goal" in relations
    assert "for_task_family" in relations
    assert "from_agent" in relations
    assert "improves_skill" in relations
    assert "lesson_platform" in relations
