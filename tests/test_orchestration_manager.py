import json
from pathlib import Path

import pytest

from modules.orchestration_manager import OrchestrationManager


@pytest.fixture
def manager(tmp_path: Path) -> OrchestrationManager:
    sqlite_path = str(tmp_path / "workflow.db")
    return OrchestrationManager(sqlite_path=sqlite_path)


def test_session_flow(manager: OrchestrationManager):
    manager.create_session("goal_alpha", ["step 1", "step 2"], "trace_alpha", thread_id="thread-alpha")
    assert manager.get_plan("goal_alpha") == ["step 1", "step 2"]
    assert manager.next_step_index("goal_alpha") == 0

    manager.mark_step_executing("goal_alpha", 0)
    manager.record_step_result("goal_alpha", 0, "completed")
    assert manager.next_step_index("goal_alpha") == 1

    manager.record_step_result("goal_alpha", 1, "waiting_approval")
    session = manager.get_session("goal_alpha")
    assert session["state"] == "waiting_approval"

    manager.resume_session("goal_alpha")
    session = manager.get_session("goal_alpha")
    assert session["state"] == "executing"
    assert manager.next_step_index("goal_alpha") == 1

    pending = manager.list_pending_sessions()
    assert any(s["goal_id"] == "goal_alpha" for s in pending)


def test_step_status_tracking(manager: OrchestrationManager):
    manager.create_session("goal_beta", ["A", "B"], "trace_beta", thread_id="thread-beta")
    manager.record_step_result("goal_beta", 0, "failed", detail="oops")
    status = manager.fetch_step_status("goal_beta", 0)
    assert status["status"] == "failed"
    assert status["detail"] == "oops"


def test_list_sessions_and_actions(manager: OrchestrationManager):
    manager.create_session("goal_gamma", ["one", "two"], "trace_gamma", thread_id="thread-gamma")
    sessions = manager.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["plan_length"] == 2
    assert sessions[0]["state"] == "executing"

    manager.record_step_result("goal_gamma", 0, "completed")
    manager.record_step_result("goal_gamma", 1, "waiting_approval")
    assert manager.get_session("goal_gamma")["state"] == "waiting_approval"

    manager.cancel_session("goal_gamma", reason="test_cancel")
    session = manager.get_session("goal_gamma")
    assert session["state"] == "cancelled"
    steps = manager.list_steps("goal_gamma")
    assert all(step["status"] == "cancelled" for step in steps)

    manager.reset_session("goal_gamma", reason="test_reset")
    session = manager.get_session("goal_gamma")
    assert session["state"] == "executing"
    steps = manager.list_steps("goal_gamma")
    assert all(step["status"] == "pending" for step in steps)
