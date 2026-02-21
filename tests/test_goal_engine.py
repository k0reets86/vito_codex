"""Тесты goal_engine.py."""

import time
from datetime import datetime, timezone, timedelta

from goal_engine import Goal, GoalEngine, GoalPriority, GoalStatus


def test_create_goal():
    ge = GoalEngine()
    goal = ge.create_goal(
        title="Test Goal",
        description="Test description",
        priority=GoalPriority.HIGH,
        source="test",
        estimated_cost_usd=1.50,
        estimated_roi=10.0,
    )
    assert goal.title == "Test Goal"
    assert goal.priority == GoalPriority.HIGH
    assert goal.status == GoalStatus.PENDING
    assert goal.source == "test"
    assert goal.estimated_cost_usd == 1.50
    assert goal.estimated_roi == 10.0
    assert goal.goal_id in ge._goals


def test_plan_goal():
    ge = GoalEngine()
    goal = ge.create_goal("Plan Test", "desc")
    ge.plan_goal(goal.goal_id, ["step1", "step2", "step3"])
    assert goal.status == GoalStatus.PLANNING
    assert len(goal.plan) == 3


def test_plan_goal_nonexistent():
    ge = GoalEngine()
    ge.plan_goal("nonexistent", ["step1"])  # не должен падать


def test_start_execution():
    ge = GoalEngine()
    goal = ge.create_goal("Exec Test", "desc", estimated_cost_usd=1.0)
    ge.plan_goal(goal.goal_id, ["step1"])
    result = ge.start_execution(goal.goal_id)
    assert result is True
    assert goal.status == GoalStatus.EXECUTING
    assert goal.started_at is not None


def test_start_execution_over_budget():
    ge = GoalEngine()
    goal = ge.create_goal("Over Budget", "desc", estimated_cost_usd=999.0)
    ge.plan_goal(goal.goal_id, ["step1"])
    result = ge.start_execution(goal.goal_id)
    assert result is False
    assert goal.status == GoalStatus.WAITING_APPROVAL


def test_complete_goal():
    ge = GoalEngine()
    goal = ge.create_goal("Complete Test", "desc")
    ge.plan_goal(goal.goal_id, ["step1"])
    ge.start_execution(goal.goal_id)
    ge.complete_goal(goal.goal_id, {"output": "done"}, lessons="learned something")
    assert goal.status == GoalStatus.COMPLETED
    assert goal.completed_at is not None
    assert goal.lessons_learned == "learned something"


def test_fail_goal():
    ge = GoalEngine()
    goal = ge.create_goal("Fail Test", "desc")
    ge.plan_goal(goal.goal_id, ["step1"])
    ge.start_execution(goal.goal_id)
    ge.fail_goal(goal.goal_id, "timeout")
    assert goal.status == GoalStatus.FAILED
    assert goal.results["failure_reason"] == "timeout"


def test_get_next_goal_priority_order():
    ge = GoalEngine()
    low = ge.create_goal("Low", "desc", priority=GoalPriority.LOW)
    high = ge.create_goal("High", "desc", priority=GoalPriority.HIGH)
    critical = ge.create_goal("Critical", "desc", priority=GoalPriority.CRITICAL)

    next_goal = ge.get_next_goal()
    assert next_goal.goal_id == critical.goal_id


def test_get_next_goal_roi_tiebreaker():
    ge = GoalEngine()
    low_roi = ge.create_goal("Low ROI", "desc", priority=GoalPriority.MEDIUM, estimated_roi=1.0)
    high_roi = ge.create_goal("High ROI", "desc", priority=GoalPriority.MEDIUM, estimated_roi=50.0)

    next_goal = ge.get_next_goal()
    assert next_goal.goal_id == high_roi.goal_id


def test_get_next_goal_none_when_empty():
    ge = GoalEngine()
    assert ge.get_next_goal() is None


def test_get_next_goal_skips_non_pending():
    ge = GoalEngine()
    goal = ge.create_goal("Done", "desc")
    ge.plan_goal(goal.goal_id, ["s1"])
    ge.start_execution(goal.goal_id)
    ge.complete_goal(goal.goal_id, {})
    assert ge.get_next_goal() is None


def test_escalation_after_30_min():
    ge = GoalEngine()
    goal = ge.create_goal("Waiting", "desc", estimated_cost_usd=999.0)
    ge.plan_goal(goal.goal_id, ["step1"])
    ge.start_execution(goal.goal_id)  # → WAITING_APPROVAL
    # Имитируем что цель создана 40 минут назад
    goal.created_at = datetime.now(timezone.utc) - timedelta(minutes=40)

    pending = ge.create_goal("Pending", "desc", priority=GoalPriority.LOW)
    ge.get_next_goal()
    assert goal.priority == GoalPriority.CRITICAL


def test_get_all_goals():
    ge = GoalEngine()
    ge.create_goal("A", "desc")
    ge.create_goal("B", "desc")
    ge.create_goal("C", "desc")
    assert len(ge.get_all_goals()) == 3


def test_get_all_goals_filter_status():
    ge = GoalEngine()
    g1 = ge.create_goal("A", "desc")
    g2 = ge.create_goal("B", "desc")
    ge.plan_goal(g1.goal_id, ["s1"])
    ge.start_execution(g1.goal_id)
    ge.complete_goal(g1.goal_id, {})
    assert len(ge.get_all_goals(GoalStatus.COMPLETED)) == 1
    assert len(ge.get_all_goals(GoalStatus.PENDING)) == 1


def test_get_stats():
    ge = GoalEngine()
    g1 = ge.create_goal("A", "desc", estimated_cost_usd=2.0)
    g2 = ge.create_goal("B", "desc", estimated_cost_usd=3.0)
    ge.plan_goal(g1.goal_id, ["s1"])
    ge.start_execution(g1.goal_id)
    ge.complete_goal(g1.goal_id, {})

    stats = ge.get_stats()
    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["success_rate"] == 1.0
    assert stats["total_estimated_cost"] == 5.0


def test_goal_dataclass_defaults():
    goal = Goal(goal_id="test", title="Test", description="desc")
    assert goal.priority == GoalPriority.MEDIUM
    assert goal.status == GoalStatus.PENDING
    assert goal.source == "system"
    assert goal.plan == []
    assert goal.results == {}
    assert goal.parent_goal_id is None
