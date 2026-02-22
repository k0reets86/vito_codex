"""Тесты decision_loop.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decision_loop import DecisionLoop, TaskType, TICK_INTERVAL, STEP_TIMEOUT, STEP_MAX_RETRIES
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
def dl(loop_deps):
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
    dl.memory.store_knowledge.assert_called_once()


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
