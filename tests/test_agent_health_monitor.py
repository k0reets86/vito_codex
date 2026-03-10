import pytest

from modules.agent_feedback import AgentFeedback
from modules.agent_health_monitor import AgentHealthMonitor
from modules.data_lake import DataLake
from modules.failure_memory import FailureMemory


def test_agent_health_monitor_builds_ranked_report(tmp_path):
    db = str(tmp_path / "health.db")
    lake = DataLake(sqlite_path=db)
    feedback = AgentFeedback(sqlite_path=db)
    failures = FailureMemory(sqlite_path=db)

    lake.record(agent="good_agent", task_type="task", status="success")
    lake.record(agent="good_agent", task_type="task", status="success")
    lake.record(agent="bad_agent", task_type="task", status="failed", error="boom")
    feedback.record(agent="good_agent", task_type="task", success=True, output={"ok": True})
    feedback.record(agent="bad_agent", task_type="task", success=False, error="boom")
    failures.record(agent="bad_agent", task_type="task", detail="task", error="boom")

    report = AgentHealthMonitor(sqlite_path=db).build_report(days=30, limit=20)
    assert report["agent_count"] >= 2
    rows = {row["agent"]: row for row in report["agents"]}
    assert rows["good_agent"]["state"] == "healthy"
    assert rows["good_agent"]["health_score"] > rows["bad_agent"]["health_score"]
    assert rows["bad_agent"]["state"] in {"degraded", "critical"}
