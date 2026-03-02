"""Тесты decision_loop.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decision_loop import DecisionLoop, TaskType, TICK_INTERVAL, STEP_TIMEOUT, STEP_MAX_RETRIES
from config.settings import settings
from goal_engine import GoalEngine, GoalPriority, GoalStatus


@pytest.fixture
def loop_deps(tmp_path):
    """Зависимости DecisionLoop с моками и изолированной SQLite."""
    ge = GoalEngine(sqlite_path=str(tmp_path / "dl_test.db"))
    llm = MagicMock()
    llm.check_daily_limit.return_value = True
    llm.get_daily_spend.return_value = 0.0
    llm.call_llm = AsyncMock(return_value="1. Step one\n2. Step two\n3. Step three")

    mem = MagicMock()
    mem.search_knowledge.return_value = []
    mem.search_skills = MagicMock(return_value=[])
    mem.store_knowledge = MagicMock()
    mem.save_skill = MagicMock()
    mem.log_error = MagicMock()
    mem.store_episode = AsyncMock()
    mem.store_to_datalake = AsyncMock()

    return ge, llm, mem


@pytest.fixture
def dl(loop_deps, monkeypatch):
    monkeypatch.setattr(settings, "PROACTIVE_ENABLED", True, raising=False)
    ge, llm, mem = loop_deps
    return DecisionLoop(goal_engine=ge, llm_router=llm, memory=mem)


# ── Инициализация ──

def test_init(dl):
    assert dl.running is False
    assert dl._tick_count == 0
    assert dl._consecutive_idle == 0


def test_stop(dl):
    dl.running = True
    dl.stop()
    assert dl.running is False


def test_get_status(dl):
    status = dl.get_status()
    assert "running" in status
    assert "tick_count" in status
    assert "daily_spend" in status
    assert "goal_stats" in status


# ── Classify step ──

def test_classify_research():
    assert DecisionLoop._classify_step("Исследование рынка Etsy") == TaskType.RESEARCH
    assert DecisionLoop._classify_step("Research competitors") == TaskType.RESEARCH
    assert DecisionLoop._classify_step("Анализ трендов") == TaskType.RESEARCH


def test_classify_strategy():
    assert DecisionLoop._classify_step("Стратегия выхода на рынок") == TaskType.STRATEGY
    assert DecisionLoop._classify_step("Evaluate approach") == TaskType.STRATEGY
    assert DecisionLoop._classify_step("Планирование бюджета") == TaskType.STRATEGY


def test_classify_code():
    assert DecisionLoop._classify_step("Написать код парсера") == TaskType.CODE
    assert DecisionLoop._classify_step("Implement script") == TaskType.CODE
    assert DecisionLoop._classify_step("Создать функцию обработки") == TaskType.CODE


def test_classify_content():
    assert DecisionLoop._classify_step("Создать контент для блога") == TaskType.CONTENT
    assert DecisionLoop._classify_step("Write blog article") == TaskType.CONTENT
    assert DecisionLoop._classify_step("Написать текст листинга") == TaskType.CONTENT


def test_classify_routine():
    assert DecisionLoop._classify_step("Загрузить файл") == TaskType.ROUTINE
    assert DecisionLoop._classify_step("Send notification") == TaskType.ROUTINE


# ── Tick ──

@pytest.mark.asyncio
async def test_tick_idle(dl):
    await dl._tick()
    assert dl._tick_count == 1
    assert dl._consecutive_idle == 1


@pytest.mark.asyncio
async def test_tick_processes_goal(dl):
    dl.goal_engine.create_goal("Test Goal", "Do something", priority=GoalPriority.HIGH)
    await dl._tick()
    assert dl._tick_count == 1
    assert dl._consecutive_idle == 0


@pytest.mark.asyncio
async def test_tick_budget_exhausted(dl):
    dl.llm_router.check_daily_limit.return_value = False
    await dl._tick()
    assert dl._tick_count == 1


# ── Idle action ──

@pytest.mark.asyncio
async def test_idle_no_action_first_time(dl):
    dl._consecutive_idle = 1
    await dl._idle_action()
    # При idle <= 1 ничего не создаётся
    assert len(dl.goal_engine._goals) == 0


@pytest.mark.asyncio
async def test_idle_creates_research_every_6(dl):
    dl._consecutive_idle = 6  # кратно 6
    await dl._idle_action()
    assert len(dl.goal_engine._goals) == 1
    goal = list(dl.goal_engine._goals.values())[0]
    assert goal.priority == GoalPriority.BACKGROUND
    assert goal.source == "proactive_daily"


@pytest.mark.asyncio
async def test_idle_skips_non_multiple_of_6(dl):
    dl._consecutive_idle = 4
    await dl._idle_action()
    assert len(dl.goal_engine._goals) == 0


# ── Plan goal ──

@pytest.mark.asyncio
async def test_plan_goal_returns_steps(dl):
    goal = dl.goal_engine.create_goal("Plan Test", "Test planning")
    steps = await dl._plan_goal(goal)
    assert len(steps) > 0
    assert len(steps) <= 7


@pytest.mark.asyncio
async def test_plan_goal_llm_fails(dl):
    dl.llm_router.call_llm = AsyncMock(return_value=None)
    goal = dl.goal_engine.create_goal("Fail Plan", "desc")
    steps = await dl._plan_goal(goal)
    assert steps == []


@pytest.mark.asyncio
async def test_plan_goal_uses_memory(dl):
    dl.memory.search_knowledge.return_value = [
        {"text": "Previous experience with Etsy templates"}
    ]
    goal = dl.goal_engine.create_goal("Etsy", "Create Etsy template")
    await dl._plan_goal(goal)
    dl.memory.search_knowledge.assert_called_once()


# ── Execute step ──

@pytest.mark.asyncio
async def test_execute_step_success(dl):
    goal = dl.goal_engine.create_goal("Exec", "desc")
    result = await dl._execute_step(goal, "Research market")
    assert result["status"] == "completed"
    assert "output" in result


@pytest.mark.asyncio
async def test_execute_step_failure(dl):
    dl.llm_router.call_llm = AsyncMock(return_value=None)
    goal = dl.goal_engine.create_goal("Exec", "desc")
    result = await dl._execute_step(goal, "Do something")
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_execute_step_policy_blocked(dl):
    dl.operator_policy = MagicMock()
    dl.operator_policy.is_tool_allowed.return_value = (False, "owner_block")
    dl.operator_policy.check_actor_budget.return_value = {"allowed": True}
    goal = dl.goal_engine.create_goal("Exec", "desc")
    result = await dl._execute_step(goal, "Research market")
    assert result["status"] == "failed"
    assert "Policy blocked" in result["error"]


@pytest.mark.asyncio
async def test_execute_step_exception(dl):
    dl.llm_router.call_llm = AsyncMock(side_effect=RuntimeError("LLM error"))
    goal = dl.goal_engine.create_goal("Exec", "desc")
    result = await dl._execute_step(goal, "Do something")
    assert result["status"] == "failed"
    assert "LLM error" in result["error"]


# ── Full goal cycle ──

@pytest.mark.asyncio
async def test_process_goal_full_cycle(dl):
    goal = dl.goal_engine.create_goal("Full Cycle", "Test full cycle", estimated_cost_usd=0.5)
    await dl._process_goal(goal)
    assert goal.status == GoalStatus.COMPLETED
    dl.memory.save_skill.assert_called_once()
    assert dl.memory.store_knowledge.call_count >= 1


@pytest.mark.asyncio
async def test_process_goal_plan_fails(dl):
    dl.llm_router.call_llm = AsyncMock(return_value=None)
    goal = dl.goal_engine.create_goal("No Plan", "desc")
    await dl._process_goal(goal)
    assert goal.status == GoalStatus.FAILED


@pytest.mark.asyncio
async def test_process_goal_waiting_approval(dl):
    goal = dl.goal_engine.create_goal("Expensive", "desc", estimated_cost_usd=999.0)
    await dl._process_goal(goal)
    assert goal.status == GoalStatus.WAITING_APPROVAL


@pytest.mark.asyncio
async def test_execute_goal_waiting_approval_mid_step(dl):
    goal = dl.goal_engine.create_goal("Need Approval", "desc")
    goal.plan = ["Step 1", "Step 2"]
    dl.goal_engine.start_execution(goal.goal_id)
    with patch.object(dl, "_execute_step_with_retry", AsyncMock(return_value={"status": "waiting_approval", "error": "pending"})):
        results = await dl._execute_goal(goal)
    assert results.get("waiting_approval") is True
    assert goal.status == GoalStatus.WAITING_APPROVAL


# ── Learn from goal ──

@pytest.mark.asyncio
async def test_learn_success(dl):
    goal = dl.goal_engine.create_goal("Learn", "desc")
    goal.plan = ["s1", "s2"]
    results = {"steps_completed": 2, "steps_total": 2, "duration_ms": 100}
    await dl._learn_from_goal(goal, results)
    assert goal.status == GoalStatus.COMPLETED
    dl.memory.save_skill.assert_called()
    dl.memory.store_knowledge.assert_called()


@pytest.mark.asyncio
async def test_learn_partial_failure(dl):
    goal = dl.goal_engine.create_goal("Partial", "desc")
    goal.plan = ["s1", "s2", "s3"]
    results = {"steps_completed": 1, "steps_total": 3}
    await dl._learn_from_goal(goal, results)
    assert goal.status == GoalStatus.FAILED
    dl.memory.log_error.assert_called()


# ── Retry & Timeout ──

@pytest.mark.asyncio
async def test_execute_step_with_retry_succeeds_first_try(dl):
    goal = dl.goal_engine.create_goal("Retry", "desc")
    result = await dl._execute_step_with_retry(goal, "Research market", 1)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_step_with_retry_succeeds_on_second(dl):
    """Step fails first, succeeds on second attempt."""
    call_count = 0

    async def flaky_step(g, s):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"status": "failed", "error": "transient"}
        return {"status": "completed", "output": "ok"}

    with patch.object(dl, "_execute_step", side_effect=flaky_step):
        goal = dl.goal_engine.create_goal("Retry2", "desc")
        result = await dl._execute_step_with_retry(goal, "do thing", 1)

    assert result["status"] == "completed"
    assert call_count == 2


@pytest.mark.asyncio
async def test_execute_step_with_retry_exhausted(dl):
    """Fails all STEP_MAX_RETRIES attempts."""
    async def always_fail(g, s):
        return {"status": "failed", "error": "persistent"}

    with patch.object(dl, "_execute_step", side_effect=always_fail):
        goal = dl.goal_engine.create_goal("Fail", "desc")
        result = await dl._execute_step_with_retry(goal, "do thing", 1)

    assert result["status"] == "failed"
    assert "persistent" in result["error"]


@pytest.mark.asyncio
async def test_execute_step_with_retry_timeout(dl):
    """Step hangs beyond STEP_TIMEOUT → retried."""
    call_count = 0

    async def slow_then_ok(g, s):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            await asyncio.sleep(999)  # will be cancelled by timeout
        return {"status": "completed", "output": "finally"}

    with patch.object(dl, "_execute_step", side_effect=slow_then_ok), \
         patch("decision_loop.STEP_TIMEOUT", 0.05):
        goal = dl.goal_engine.create_goal("Slow", "desc")
        result = await dl._execute_step_with_retry(goal, "slow step", 1)

    assert result["status"] == "completed"
    assert call_count == 3


@pytest.mark.asyncio
async def test_execute_step_with_retry_all_timeout(dl):
    """All retries time out."""
    async def always_slow(g, s):
        await asyncio.sleep(999)
        return {"status": "completed", "output": "never"}

    with patch.object(dl, "_execute_step", side_effect=always_slow), \
         patch("decision_loop.STEP_TIMEOUT", 0.05):
        goal = dl.goal_engine.create_goal("AllSlow", "desc")
        result = await dl._execute_step_with_retry(goal, "infinite step", 1)

    assert result["status"] == "failed"
    assert "Таймаут" in result["error"]


@pytest.mark.asyncio
async def test_execute_step_with_retry_stops_when_cancelled(dl):
    dl.set_cancel_state(MagicMock(is_cancelled=MagicMock(return_value=True)))
    with patch.object(dl, "_execute_step", AsyncMock(return_value={"status": "completed", "output": "ok"})) as ex:
        goal = dl.goal_engine.create_goal("Cancelled", "desc")
        result = await dl._execute_step_with_retry(goal, "do thing", 1)
    assert result["status"] == "failed"
    assert result.get("cancelled") is True
    ex.assert_not_called()


def test_trace_handoff_includes_interrupt_goal_thread_context(dl):
    dl._current_interrupt_id = 99
    dl._current_goal_id = "goal_1"
    dl._current_thread_id = "thread_1"
    with patch("decision_loop.DataLake") as dlake:
        instance = dlake.return_value
        instance.record_handoff = MagicMock()
        dl._trace_handoff(
            from_agent="decision_loop",
            to_agent="agent_registry",
            capability="publish",
            step="run publish step",
            status="start",
        )
    kwargs = instance.record_handoff.call_args.kwargs
    assert kwargs["context"]["interrupt_id"] == 99
    assert kwargs["context"]["goal_id"] == "goal_1"
    assert kwargs["context"]["thread_id"] == "thread_1"


def test_trace_handoff_enriches_interrupt_metadata(dl):
    intr_id = dl.interrupts.open_interrupt(
        goal_id="goal_meta",
        interrupt_type="owner_approval_required",
        reason="budget_gate",
        step_num=0,
        thread_id="goal_goal_meta",
    )
    dl._current_interrupt_id = intr_id
    with patch("decision_loop.DataLake") as dlake:
        instance = dlake.return_value
        instance.record_handoff = MagicMock()
        dl._trace_handoff(
            from_agent="decision_loop",
            to_agent="agent_registry",
            capability="publish",
            step="run publish step",
            status="start",
            goal_id="goal_meta",
            thread_id="goal_goal_meta",
        )
    kwargs = instance.record_handoff.call_args.kwargs
    assert kwargs["context"]["interrupt_id"] == intr_id
    assert kwargs["context"]["interrupt_type"] == "owner_approval_required"
    assert kwargs["context"]["interrupt_status"] == "pending"


@pytest.mark.asyncio
async def test_dispatch_with_trace_records_start_and_result(dl):
    dl._current_interrupt_id = 7
    dl._current_goal_id = "goal_dispatch"
    dl._current_thread_id = "goal_goal_dispatch"
    dl.agent_registry = MagicMock()
    ok_result = MagicMock()
    ok_result.success = True
    dl.agent_registry.dispatch = AsyncMock(return_value=ok_result)

    with patch("decision_loop.DataLake") as mock_dl:
        instance = mock_dl.return_value
        instance.record_handoff = MagicMock()
        out = await dl._dispatch_with_trace(
            "research",
            step_text="Research competitors",
            step="Research competitors",
            goal_title="G",
            content="Research competitors",
        )
    assert out is ok_result
    assert instance.record_handoff.call_count == 2
    first = instance.record_handoff.call_args_list[0].kwargs
    second = instance.record_handoff.call_args_list[1].kwargs
    assert first["status"] == "start"
    assert second["status"] == "success"
    assert first["context"]["interrupt_id"] == 7
    assert first["context"]["goal_id"] == "goal_dispatch"
    assert first["context"]["thread_id"] == "goal_goal_dispatch"


@pytest.mark.asyncio
async def test_dispatch_with_trace_records_failed_on_exception(dl):
    dl.agent_registry = MagicMock()
    dl.agent_registry.dispatch = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("decision_loop.DataLake") as mock_dl:
        instance = mock_dl.return_value
        instance.record_handoff = MagicMock()
        with pytest.raises(RuntimeError):
            await dl._dispatch_with_trace(
                "content_creation",
                step_text="Create content",
                step="Create content",
                goal_title="G",
                content="Create content",
            )
    assert instance.record_handoff.call_count == 2
    first = instance.record_handoff.call_args_list[0].kwargs
    second = instance.record_handoff.call_args_list[1].kwargs
    assert first["status"] == "start"
    assert second["status"] == "failed"


@pytest.mark.asyncio
async def test_auto_resume_waiting_goal_when_interrupt_resolved(dl):
    goal = dl.goal_engine.create_goal("Auto Resume", "desc")
    goal.plan = ["step 1"]
    dl.goal_engine.wait_for_approval(goal.goal_id, reason="manual")
    dl.orchestrator.create_session(goal.goal_id, goal.plan, "trace_auto", thread_id=f"goal_{goal.goal_id}")
    dl.orchestrator.record_step_result(goal.goal_id, 0, "waiting_approval", detail="pending")
    intr_id = dl.interrupts.open_interrupt(
        goal_id=goal.goal_id,
        interrupt_type="step_approval_pending",
        reason="pending",
        step_num=1,
        thread_id=f"goal_{goal.goal_id}",
    )
    assert intr_id > 0
    dl.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="resumed")

    await dl._maybe_auto_resume_waiting_goals()

    resumed_goal = dl.goal_engine._goals[goal.goal_id]
    assert resumed_goal.status == GoalStatus.PENDING
    session = dl.orchestrator.get_session(goal.goal_id)
    assert session["state"] == "executing"
    assert dl.interrupts.count_resume_events(goal.goal_id, intr_id, action="resumed") == 1


@pytest.mark.asyncio
async def test_auto_resume_waiting_goal_respects_policy_limit(dl):
    goal = dl.goal_engine.create_goal("Auto Resume Limit", "desc")
    goal.plan = ["step 1"]
    dl.goal_engine.wait_for_approval(goal.goal_id, reason="manual")
    dl.orchestrator.create_session(goal.goal_id, goal.plan, "trace_auto_limit", thread_id=f"goal_{goal.goal_id}")
    dl.orchestrator.record_step_result(goal.goal_id, 0, "waiting_approval", detail="pending")
    intr_id = dl.interrupts.open_interrupt(
        goal_id=goal.goal_id,
        interrupt_type="step_approval_pending",
        reason="pending",
        step_num=1,
        thread_id=f"goal_{goal.goal_id}",
    )
    dl.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="resumed")
    dl.interrupts.log_resume_event(goal.goal_id, intr_id, action="resumed", reason="prior_resume")

    with patch("decision_loop.settings.AUTO_RESUME_MAX_PER_INTERRUPT", 1):
        await dl._maybe_auto_resume_waiting_goals()

    same_goal = dl.goal_engine._goals[goal.goal_id]
    assert same_goal.status == GoalStatus.WAITING_APPROVAL
    session = dl.orchestrator.get_session(goal.goal_id)
    assert session["state"] == "waiting_approval"
    assert dl.interrupts.count_resume_events(goal.goal_id, intr_id, action="skipped") == 1


@pytest.mark.asyncio
async def test_auto_cancel_waiting_goal_when_interrupt_cancelled(dl):
    goal = dl.goal_engine.create_goal("Auto Cancel", "desc")
    goal.plan = ["step 1"]
    dl.goal_engine.wait_for_approval(goal.goal_id, reason="manual")
    dl.orchestrator.create_session(goal.goal_id, goal.plan, "trace_cancel", thread_id=f"goal_{goal.goal_id}")
    dl.orchestrator.record_step_result(goal.goal_id, 0, "waiting_approval", detail="pending")
    dl.interrupts.open_interrupt(
        goal_id=goal.goal_id,
        interrupt_type="step_approval_pending",
        reason="pending",
        step_num=1,
        thread_id=f"goal_{goal.goal_id}",
    )
    dl.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="cancelled")

    await dl._maybe_auto_resume_waiting_goals()

    cancelled_goal = dl.goal_engine._goals[goal.goal_id]
    assert cancelled_goal.status == GoalStatus.FAILED
    session = dl.orchestrator.get_session(goal.goal_id)
    assert session["state"] == "cancelled"


@pytest.mark.asyncio
async def test_auto_resume_waiting_goal_skipped_when_cancelled(dl):
    goal = dl.goal_engine.create_goal("Auto Resume Blocked", "desc")
    goal.plan = ["step 1"]
    dl.goal_engine.wait_for_approval(goal.goal_id, reason="manual")
    dl.orchestrator.create_session(goal.goal_id, goal.plan, "trace_auto_blocked", thread_id=f"goal_{goal.goal_id}")
    dl.orchestrator.record_step_result(goal.goal_id, 0, "waiting_approval", detail="pending")
    dl.interrupts.open_interrupt(
        goal_id=goal.goal_id,
        interrupt_type="step_approval_pending",
        reason="pending",
        step_num=1,
        thread_id=f"goal_{goal.goal_id}",
    )
    dl.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="resumed")
    dl.set_cancel_state(MagicMock(is_cancelled=MagicMock(return_value=True)))

    await dl._maybe_auto_resume_waiting_goals()

    same_goal = dl.goal_engine._goals[goal.goal_id]
    assert same_goal.status == GoalStatus.WAITING_APPROVAL
    session = dl.orchestrator.get_session(goal.goal_id)
    assert session["state"] == "waiting_approval"


@pytest.mark.asyncio
async def test_execute_goal_waiting_session_interrupt_cancelled_stays_cancelled(dl):
    goal = dl.goal_engine.create_goal("Exec Cancelled Interrupt", "desc")
    goal.plan = ["step 1"]
    dl.goal_engine.wait_for_approval(goal.goal_id, reason="manual")
    dl.orchestrator.create_session(goal.goal_id, goal.plan, "trace_exec_cancel", thread_id=f"goal_{goal.goal_id}")
    dl.orchestrator.record_step_result(goal.goal_id, 0, "waiting_approval", detail="pending")
    dl.interrupts.open_interrupt(
        goal_id=goal.goal_id,
        interrupt_type="step_approval_pending",
        reason="pending",
        step_num=1,
        thread_id=f"goal_{goal.goal_id}",
    )
    dl.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="cancelled")

    result = await dl._execute_goal(goal)

    assert result.get("cancelled") is True
    assert result.get("cancel_reason") == "interrupt_cancelled"
    assert dl.goal_engine._goals[goal.goal_id].status == GoalStatus.FAILED
    session = dl.orchestrator.get_session(goal.goal_id)
    assert session["state"] == "cancelled"


@pytest.mark.asyncio
async def test_execute_goal_waiting_session_resolved_respects_auto_resume_limit(dl):
    goal = dl.goal_engine.create_goal("Exec Resume Limit", "desc")
    goal.plan = ["step 1"]
    dl.goal_engine.wait_for_approval(goal.goal_id, reason="manual")
    dl.orchestrator.create_session(goal.goal_id, goal.plan, "trace_exec_limit", thread_id=f"goal_{goal.goal_id}")
    dl.orchestrator.record_step_result(goal.goal_id, 0, "waiting_approval", detail="pending")
    intr_id = dl.interrupts.open_interrupt(
        goal_id=goal.goal_id,
        interrupt_type="step_approval_pending",
        reason="pending",
        step_num=1,
        thread_id=f"goal_{goal.goal_id}",
    )
    dl.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="resumed")
    dl.interrupts.log_resume_event(goal.goal_id, intr_id, action="resumed", reason="prior_resume")

    with patch("decision_loop.settings.AUTO_RESUME_MAX_PER_INTERRUPT", 1):
        result = await dl._execute_goal(goal)

    assert result.get("waiting_approval") is True
    assert dl.goal_engine._goals[goal.goal_id].status == GoalStatus.WAITING_APPROVAL
    session = dl.orchestrator.get_session(goal.goal_id)
    assert session["state"] == "waiting_approval"
    assert dl.interrupts.count_resume_events(goal.goal_id, intr_id, action="skipped") >= 1


@pytest.mark.asyncio
async def test_tooling_governance_alert_sends_message(dl):
    dl._tick_count = 50
    dl._last_tooling_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    with patch("decision_loop.settings.TOOLING_GOVERNANCE_ALERT_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_GOVERNANCE_INTERVAL_TICKS", 1), \
         patch("decision_loop.ToolingRegistry") as reg_cls:
        reg_cls.return_value.build_governance_report.return_value = {
            "pending_contract_rotations": 1,
            "pending_stage_changes": 0,
            "pending_key_rotations": 2,
            "key_rotation_health": {"alerts": [{"key_type": "contract"}]},
            "remediations": ["Rotate keys", "Process approvals"],
        }
        await dl._maybe_run_tooling_governance_check()
    dl._comms.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_tooling_discovery_intake_runs_and_auto_promotes(dl):
    dl._tick_count = 100
    dl._last_tooling_discovery_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    with patch("decision_loop.settings.TOOLING_DISCOVERY_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_MAX_PER_TICK", 2), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ROLLOUT_STAGE", "canary"), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_CANARY_PERCENT", 50), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_SOURCES", '[{"source":"scan","adapter_key":"weather","protocol":"openapi","endpoint":"https://api.example.com/openapi.json"}]'), \
         patch("decision_loop.ToolingDiscovery") as dcls:
        d = dcls.return_value
        d.discover_from_sources.return_value = {"ok": True, "processed": 1, "duplicates": 0, "review_required": 0, "promoted": 1}
        await dl._maybe_run_tooling_discovery_intake()
    d.discover_from_sources.assert_called_once()
    dl._comms.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_tooling_discovery_intake_alerts_on_review_required(dl):
    dl._tick_count = 100
    dl._last_tooling_discovery_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    with patch("decision_loop.settings.TOOLING_DISCOVERY_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_MAX_PER_TICK", 2), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED", False), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ROLLOUT_STAGE", "canary"), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_CANARY_PERCENT", 50), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_SOURCES", '[{"source":"scan","adapter_key":"bad","protocol":"openapi","endpoint":"https://bad.example.com/spec.json"}]'), \
         patch("decision_loop.ToolingDiscovery") as dcls:
        d = dcls.return_value
        d.discover_from_sources.return_value = {"ok": True, "processed": 1, "duplicates": 0, "review_required": 1, "promoted": 0}
        await dl._maybe_run_tooling_discovery_intake()
    dl._comms.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_tooling_discovery_intake_alert_includes_policy_blocked(dl):
    dl._tick_count = 100
    dl._last_tooling_discovery_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    with patch("decision_loop.settings.TOOLING_DISCOVERY_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_MAX_PER_TICK", 2), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED", False), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ROLLOUT_STAGE", "canary"), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_CANARY_PERCENT", 50), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_SOURCES", '[{"source":"scan","adapter_key":"bad","protocol":"openapi","endpoint":"http://bad.example.com/spec.json"}]'), \
         patch("decision_loop.ToolingDiscovery") as dcls:
        d = dcls.return_value
        d.discover_from_sources.return_value = {
            "ok": True,
            "processed": 1,
            "duplicates": 0,
            "review_required": 1,
            "policy_blocked": 1,
            "policy_block_reasons": {"endpoint_https_required": 1},
            "promoted": 0,
        }
        await dl._maybe_run_tooling_discovery_intake()
    dl._comms.send_message.assert_called_once()
    sent_msg = str(dl._comms.send_message.call_args.args[0] or "")
    assert "policy_blocked: 1" in sent_msg
    assert "policy_block_reasons: endpoint_https_required=1" in sent_msg


@pytest.mark.asyncio
async def test_tooling_discovery_intake_auto_pauses_on_policy_block_threshold(dl):
    dl._tick_count = 100
    dl._last_tooling_discovery_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    with patch("decision_loop.settings.TOOLING_DISCOVERY_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_MAX_PER_TICK", 3), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED", False), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ROLLOUT_STAGE", "canary"), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_CANARY_PERCENT", 50), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_AUTO_PAUSE_ON_POLICY_BLOCK", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_POLICY_BLOCK_THRESHOLD", 2), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_SOURCES", '[{"source":"scan","adapter_key":"bad","protocol":"openapi","endpoint":"http://bad.example.com/spec.json"}]'), \
         patch("decision_loop.ToolingDiscovery") as dcls, \
         patch("decision_loop.apply_safe_action", return_value={"TOOLING_DISCOVERY_ENABLED": "false"}) as apply_mock:
        d = dcls.return_value
        d.discover_from_sources.return_value = {"ok": True, "processed": 2, "duplicates": 0, "review_required": 0, "policy_blocked": 2, "promoted": 0}
        await dl._maybe_run_tooling_discovery_intake()
    apply_mock.assert_called_once_with("disable_discovery_intake")
    dl._comms.send_message.assert_called_once()
    sent_msg = str(dl._comms.send_message.call_args.args[0] or "")
    assert "auto_paused: true" in sent_msg


@pytest.mark.asyncio
async def test_tooling_discovery_intake_auto_pauses_on_policy_block_rate(dl):
    dl._tick_count = 100
    dl._last_tooling_discovery_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    with patch("decision_loop.settings.TOOLING_DISCOVERY_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_MAX_PER_TICK", 5), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED", False), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ROLLOUT_STAGE", "canary"), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_CANARY_PERCENT", 50), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_AUTO_PAUSE_ON_POLICY_BLOCK", True), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_POLICY_BLOCK_THRESHOLD", 10), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_POLICY_BLOCK_RATE_THRESHOLD", 0.6), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_POLICY_BLOCK_RATE_MIN_PROCESSED", 3), \
         patch("decision_loop.settings.TOOLING_DISCOVERY_SOURCES", '[{"source":"scan","adapter_key":"bad","protocol":"openapi","endpoint":"http://bad.example.com/spec.json"}]'), \
         patch("decision_loop.ToolingDiscovery") as dcls, \
         patch("decision_loop.apply_safe_action", return_value={"TOOLING_DISCOVERY_ENABLED": "false"}) as apply_mock:
        d = dcls.return_value
        d.discover_from_sources.return_value = {"ok": True, "processed": 5, "duplicates": 0, "review_required": 0, "policy_blocked": 4, "promoted": 0}
        await dl._maybe_run_tooling_discovery_intake()
    apply_mock.assert_called_once_with("disable_discovery_intake")
    dl._comms.send_message.assert_called_once()
    sent_msg = str(dl._comms.send_message.call_args.args[0] or "")
    assert "auto_paused: true" in sent_msg
    assert "rate=0.80" in sent_msg


@pytest.mark.asyncio
async def test_tooling_governance_alert_skips_when_clean(dl):
    dl._tick_count = 50
    dl._last_tooling_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    with patch("decision_loop.settings.TOOLING_GOVERNANCE_ALERT_ENABLED", True), \
         patch("decision_loop.settings.TOOLING_GOVERNANCE_INTERVAL_TICKS", 1), \
         patch("decision_loop.ToolingRegistry") as reg_cls:
        reg_cls.return_value.build_governance_report.return_value = {
            "pending_contract_rotations": 0,
            "pending_stage_changes": 0,
            "pending_key_rotations": 0,
            "key_rotation_health": {"alerts": []},
            "remediations": [],
        }
        await dl._maybe_run_tooling_governance_check()
    dl._comms.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_memory_weekly_report_alert_on_low_quality(dl):
    dl._tick_count = 2500
    dl._last_memory_weekly_report_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_retention_report.return_value = {"summary": {"quality_score": 0.4}, "alerts": [{"code": "low_quality"}]}
    reporter.per_skill_quality.return_value = [{"skill_name": "s1", "learning_health": 0.2}]
    with patch("decision_loop.settings.MEMORY_WEEKLY_REPORT_ENABLED", True), \
         patch("decision_loop.settings.MEMORY_WEEKLY_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.MEMORY_WEEKLY_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.MemorySkillReporter", return_value=reporter):
        await dl._maybe_run_memory_weekly_report()
    reporter.persist_markdown.assert_called_once()
    dl._comms.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_memory_weekly_report_no_alert_when_clean(dl):
    dl._tick_count = 2500
    dl._last_memory_weekly_report_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_retention_report.return_value = {"summary": {"quality_score": 0.9}, "alerts": []}
    reporter.per_skill_quality.return_value = [{"skill_name": "s1", "learning_health": 0.8}]
    with patch("decision_loop.settings.MEMORY_WEEKLY_REPORT_ENABLED", True), \
         patch("decision_loop.settings.MEMORY_WEEKLY_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.MEMORY_WEEKLY_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.MemorySkillReporter", return_value=reporter):
        await dl._maybe_run_memory_weekly_report()
    dl._comms.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_governance_report_alert_on_warning(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {"status": "warning", "remediations": ["Rotate keys", "Fix prompts"]}
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter):
        await dl._maybe_run_weekly_governance_report()
    reporter.persist_markdown.assert_called_once()
    dl._comms.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_weekly_governance_report_skips_alert_when_ok(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {"status": "ok", "remediations": []}
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter):
        await dl._maybe_run_weekly_governance_report()
    dl._comms.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_applies_safe_actions(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["Rotate keys"],
        "safe_action_suggestions": [
            {"action": "apply_profile_economy", "priority": 1, "reason": "cost anomaly"},
            {"action": "enable_guardrails_block", "priority": 2, "reason": "fail rate"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", return_value={"MODEL_ACTIVE_PROFILE": "economy"}) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    apply_mock.assert_called_once_with("apply_profile_economy")


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_uses_highest_score(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["Tooling risk"],
        "safe_action_suggestions": [
            {"action": "apply_profile_economy", "priority": 1, "score": 5, "reason": "cost"},
            {"action": "disable_tooling_live", "priority": 2, "score": 9, "reason": "key alerts"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_ON_WARNING", False), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", return_value={"TOOLING_RUN_LIVE_ENABLED": "false"}) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    apply_mock.assert_called_once_with("disable_tooling_live")


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_can_apply_on_warning_when_enabled(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "warning",
        "remediations": ["Provider degraded"],
        "safe_action_suggestions": [
            {"action": "set_notify_minimal", "priority": 3, "score": 2, "reason": "reduce noise"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_ON_WARNING", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", return_value={"NOTIFY_MODE": "minimal"}) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    apply_mock.assert_called_once_with("set_notify_minimal")


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_reports_noop_skips(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["Already in safe mode"],
        "safe_action_suggestions": [
            {"action": "set_notify_minimal", "priority": 3, "score": 2, "reason": "already applied"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", return_value={}) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    apply_mock.assert_called_once_with("set_notify_minimal")
    dl._comms.send_message.assert_called_once()
    sent_msg = str(dl._comms.send_message.call_args.args[0] or "")
    assert "auto_skipped_noop: set_notify_minimal" in sent_msg


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_skips_duplicate_actions(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["De-dup test"],
        "safe_action_suggestions": [
            {"action": "set_notify_minimal", "priority": 1, "score": 9, "reason": "top"},
            {"action": "set_notify_minimal", "priority": 2, "score": 5, "reason": "duplicate"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 2), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", return_value={"NOTIFY_MODE": "minimal"}) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    apply_mock.assert_called_once_with("set_notify_minimal")
    dl._comms.send_message.assert_called_once()
    sent_msg = str(dl._comms.send_message.call_args.args[0] or "")
    assert "auto_skipped_duplicate: set_notify_minimal" in sent_msg


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_skips_invalid_actions(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["Invalid action test"],
        "safe_action_suggestions": [
            {"action": "unknown_action", "priority": 1, "score": 9, "reason": "invalid"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", return_value={}) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    apply_mock.assert_not_called()
    dl._comms.send_message.assert_called_once()
    sent_msg = str(dl._comms.send_message.call_args.args[0] or "")
    assert "auto_skipped_invalid: unknown_action" in sent_msg


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_budget_uses_unique_actions(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["Budget unique actions test"],
        "safe_action_suggestions": [
            {"action": "set_notify_minimal", "priority": 1, "score": 9, "reason": "top"},
            {"action": "set_notify_minimal", "priority": 2, "score": 8, "reason": "duplicate"},
            {"action": "enable_guardrails_block", "priority": 3, "score": 7, "reason": "second unique"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 2), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", side_effect=[{"NOTIFY_MODE": "minimal"}, {"GUARDRAILS_BLOCK_ON_INJECTION": "true"}]) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    assert apply_mock.call_count == 2
    assert apply_mock.call_args_list[0].args[0] == "set_notify_minimal"
    assert apply_mock.call_args_list[1].args[0] == "enable_guardrails_block"


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_noop_does_not_consume_budget(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["No-op budget test"],
        "safe_action_suggestions": [
            {"action": "set_notify_minimal", "priority": 1, "score": 9, "reason": "already applied"},
            {"action": "enable_guardrails_block", "priority": 2, "score": 8, "reason": "needs apply"},
        ],
    }
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 1), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.apply_safe_action", side_effect=[{}, {"GUARDRAILS_BLOCK_ON_INJECTION": "true"}]) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    assert apply_mock.call_count == 2
    assert apply_mock.call_args_list[0].args[0] == "set_notify_minimal"
    assert apply_mock.call_args_list[1].args[0] == "enable_guardrails_block"


@pytest.mark.asyncio
async def test_weekly_governance_auto_remediation_uses_ranker_and_records_outcomes(dl):
    dl._tick_count = 5000
    dl._last_weekly_governance_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "remediations": ["Trust-ranked remediation"],
        "safe_action_suggestions": [
            {"action": "set_notify_minimal", "priority": 2, "score": 3},
            {"action": "enable_guardrails_block", "priority": 1, "score": 3},
        ],
    }
    ranked = [
        {"action": "enable_guardrails_block", "priority": 1, "score": 3, "effective_score": 4.0},
        {"action": "set_notify_minimal", "priority": 2, "score": 3, "effective_score": 2.0},
    ]
    with patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE", True), \
         patch("decision_loop.settings.WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 2), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.rank_safe_action_suggestions", return_value=ranked) as rank_mock, \
         patch("decision_loop.record_safe_action_outcome") as record_mock, \
         patch("decision_loop.apply_safe_action", side_effect=[{"GUARDRAILS_BLOCK_ON_INJECTION": "true"}, {}]) as apply_mock:
        await dl._maybe_run_weekly_governance_report()
    rank_mock.assert_called_once()
    assert apply_mock.call_args_list[0].args[0] == "enable_guardrails_block"
    assert apply_mock.call_args_list[1].args[0] == "set_notify_minimal"
    recorded_outcomes = [tuple(call.args[:2]) for call in record_mock.call_args_list]
    assert ("enable_guardrails_block", "applied") in recorded_outcomes
    assert ("set_notify_minimal", "noop") in recorded_outcomes


@pytest.mark.asyncio
async def test_self_learning_maintenance_runs_recalibration_and_cleanup(dl):
    dl._tick_count = 500
    dl._last_self_learning_maintenance_tick = 0
    sl = MagicMock()
    sl.recalibrate_thresholds.return_value = {"ok": True, "updated": 2}
    sl.sync_promotion_outcomes_from_tests.return_value = {"ok": True, "inserted": 1}
    sl.remediate_degraded_promoted_skills.return_value = {"ok": True, "remediated": 1, "queued_jobs": 1}
    sl.cleanup_old_test_jobs.return_value = {"ok": True, "deleted": 3}
    dl.self_learning = sl
    with patch("decision_loop.settings.SELF_LEARNING_ENABLED", True), \
         patch("decision_loop.settings.SELF_LEARNING_MAINTENANCE_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.SELF_LEARNING_MAINTENANCE_DAYS", 45), \
         patch("decision_loop.settings.SELF_LEARNING_MAINTENANCE_MIN_LESSONS", 4), \
         patch("decision_loop.settings.SELF_LEARNING_REMEDIATION_MAX_ACTIONS", 3), \
         patch("decision_loop.settings.SELF_LEARNING_OUTCOME_MIN_TEST_RUNS", 2), \
         patch("decision_loop.settings.SELF_LEARNING_OUTCOME_FAIL_RATE_MAX", 0.35), \
         patch("decision_loop.settings.SELF_LEARNING_TEST_JOB_RETENTION_DAYS", 90):
        await dl._maybe_run_self_learning_maintenance()
    sl.recalibrate_thresholds.assert_called_once()
    sl.sync_promotion_outcomes_from_tests.assert_called_once()
    sl.remediate_degraded_promoted_skills.assert_called_once()
    sl.cleanup_old_test_jobs.assert_called_once()


@pytest.mark.asyncio
async def test_autonomous_improvement_generates_candidates_and_alerts(dl):
    dl._tick_count = 700
    dl._last_autonomous_improvement_tick = 0
    dl._comms = MagicMock()
    dl._comms.send_message = AsyncMock(return_value=True)
    reporter = MagicMock()
    reporter.weekly_report.return_value = {
        "status": "critical",
        "safe_action_suggestions": [
            {"action": "enable_guardrails_block", "priority": 1, "score": 8, "reason": "risk"},
        ],
    }
    sl = MagicMock()
    sl.summary.return_value = {"open_test_jobs": 2, "pending_candidates": 1}
    dl.self_learning = sl
    improver = MagicMock()
    improver.generate_candidates.return_value = {
        "created": 2,
        "candidates": [
            {"action": "enable_guardrails_block"},
            {"action": "run_self_learning_test_jobs"},
        ],
    }
    with patch("decision_loop.settings.AUTONOMOUS_IMPROVEMENT_ENABLED", True), \
         patch("decision_loop.settings.AUTONOMOUS_IMPROVEMENT_ALERTS_ENABLED", True), \
         patch("decision_loop.settings.AUTONOMOUS_IMPROVEMENT_INTERVAL_TICKS", 1), \
         patch("decision_loop.settings.AUTONOMOUS_IMPROVEMENT_MAX_CANDIDATES", 4), \
         patch("decision_loop.settings.SELF_LEARNING_ENABLED", True), \
         patch("decision_loop.GovernanceReporter", return_value=reporter), \
         patch("decision_loop.AutonomousImprovementEngine", return_value=improver):
        await dl._maybe_run_autonomous_improvement()
    improver.generate_candidates.assert_called_once()
    dl._comms.send_message.assert_awaited_once()
