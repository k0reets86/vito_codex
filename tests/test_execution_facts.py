from modules.execution_facts import ExecutionFacts


def test_recent_status_exists(tmp_path):
    db = str(tmp_path / "facts.db")
    facts = ExecutionFacts(sqlite_path=db)
    facts.record(action="platform:publish", status="daily_limit", detail="x")
    assert facts.recent_status_exists("platform:publish", "daily_limit", hours=24) is True
    assert facts.recent_status_exists("platform:publish", "published", hours=24) is False
