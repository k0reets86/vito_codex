from modules.playbook_registry import PlaybookRegistry


def test_playbook_registry_learn_and_top(tmp_path):
    db = str(tmp_path / "pb.db")
    reg = PlaybookRegistry(sqlite_path=db)
    reg.learn(agent="a1", task_type="publish", action="platform:publish", status="success", strategy={"k": "v"})
    reg.learn(agent="a1", task_type="publish", action="platform:publish", status="failed", strategy={"k": "v2"})
    rows = reg.top(limit=10)
    assert len(rows) >= 1
    r = rows[0]
    assert r["action"] == "platform:publish"
    assert r["success_count"] >= 1
    assert r["fail_count"] >= 1
