from modules.playbook_registry import PlaybookRegistry


def test_find_sorts_by_success_rate(tmp_path):
    sqlite_path = tmp_path / "playbooks.sqlite"
    reg = PlaybookRegistry(sqlite_path=str(sqlite_path))
    reg.learn(agent="research_agent", task_type="research", action="research_agent:research:a", status="success")
    reg.learn(agent="research_agent", task_type="research", action="research_agent:research:b", status="failed")
    reg.learn(agent="research_agent", task_type="research", action="research_agent:research:a", status="success")
    rows = reg.find(agent="research_agent", task_type="research", limit=10)
    assert len(rows) >= 2
    assert rows[0]["action"] == "research_agent:research:a"
