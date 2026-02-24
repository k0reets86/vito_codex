"""Тесты llm_router.py."""

import logging
import os
import tempfile
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from config.settings import settings

# Сбрасываем LogRecordFactory до стандартной чтобы extra={"agent":...} не конфликтовал
logging.setLogRecordFactory(logging.LogRecord)

from llm_router import (
    LLMRouter,
    ModelConfig,
    TaskType,
    MODEL_REGISTRY,
    TASK_MODEL_MAP,
    RouteResult,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary SQLite path for LLMRouter tests."""
    return str(tmp_path / "test_spend.db")


@pytest.fixture
def router(tmp_db):
    return LLMRouter(sqlite_path=tmp_db)


def test_model_registry_has_all_models():
    expected = {"claude-sonnet", "claude-opus", "claude-haiku", "gpt-o3", "gpt-5", "gpt-4o-mini", "perplexity", "gemini-flash"}
    assert set(MODEL_REGISTRY.keys()) == expected


def test_task_model_map_has_all_types():
    for task_type in TaskType:
        assert task_type in TASK_MODEL_MAP
        assert len(TASK_MODEL_MAP[task_type]) >= 1  # основная (fallback optional)


def test_model_config_fields():
    m = MODEL_REGISTRY["claude-sonnet"]
    assert m.provider == "anthropic"
    assert m.cost_per_1k_input > 0
    assert m.cost_per_1k_output > 0
    assert m.max_tokens > 0


def test_select_model_content(router):
    result = router.select_model(TaskType.CONTENT, estimated_tokens=1000)
    assert isinstance(result, RouteResult)
    assert result.model.provider == "anthropic"
    assert "sonnet" in result.model.model_id.lower()
    assert result.estimated_cost_usd > 0


def test_select_model_strategy(router):
    result = router.select_model(TaskType.STRATEGY)
    assert result.model.model_id in ("gpt-5", "claude-opus", "claude-opus-4-6")


def test_select_model_code(router):
    result = router.select_model(TaskType.CODE)
    assert result.model.provider == "openai"


def test_select_model_research(router):
    result = router.select_model(TaskType.RESEARCH)
    assert result.model.provider == "perplexity"


def test_select_model_routine(router):
    result = router.select_model(TaskType.ROUTINE)
    assert "gemini" in result.model.model_id.lower()  # Gemini 2.5 Flash Lite must be first (free tier)


def test_select_model_self_heal(router):
    result = router.select_model(TaskType.SELF_HEAL)
    assert result.model.provider == "openai"  # o3 / Codex first, Claude last resort


def test_select_model_needs_approval_high_cost(router):
    result = router.select_model(TaskType.STRATEGY, estimated_tokens=100000)
    assert result.needs_approval is True


def test_select_model_no_approval_low_cost(router):
    result = router.select_model(TaskType.ROUTINE, estimated_tokens=100)
    assert result.needs_approval is False


def test_calc_cost_real_usage(router):
    model = MODEL_REGISTRY["claude-haiku"]
    cost = router._calc_cost(model, input_tokens=1000, output_tokens=500)
    expected = (1000 / 1000) * model.cost_per_1k_input + (500 / 1000) * model.cost_per_1k_output
    assert abs(cost - expected) < 1e-9


def test_daily_spend_tracking(router):
    assert router.get_daily_spend() == 0.0


def test_check_daily_limit_ok(router):
    assert router.check_daily_limit() is True


def test_check_daily_limit_exceeded(router):
    # Insert a large spend directly into SQLite
    conn = router._get_sqlite()
    conn.execute(
        "INSERT INTO spend_log (date, model, task_type, cost_usd) VALUES (?, ?, ?, ?)",
        (date.today().isoformat(), "test", "routine", 999.0),
    )
    conn.commit()
    assert router.check_daily_limit() is False


def test_spend_persists_in_sqlite(router):
    router._record_spend("Claude Haiku", "routine", 100, 50, 0.05)
    router._record_spend("Claude Haiku", "routine", 200, 100, 0.10)
    assert abs(router.get_daily_spend() - 0.15) < 1e-9


@pytest.mark.asyncio
async def test_call_llm_returns_none_on_approval_needed(router):
    # Очень дорогой запрос — needs_approval
    result = await router.call_llm(
        task_type=TaskType.STRATEGY,
        prompt="test",
        estimated_tokens=500000,
    )
    assert result is None


@pytest.mark.asyncio
async def test_call_llm_with_mock(router):
    mock_text = "Test response from LLM"
    mock_cost = 0.0012

    with patch.object(router, "_call_provider", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = (mock_text, mock_cost)
        result = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="test prompt",
            estimated_tokens=100,
        )
    assert result == mock_text
    assert abs(router.get_daily_spend() - mock_cost) < 1e-9


@pytest.mark.asyncio
async def test_call_llm_cache_hit(router):
    mock_text = "Cached response"
    mock_cost = 0.001

    with patch.object(router, "_call_provider", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = (mock_text, mock_cost)
        first = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="cache me",
            estimated_tokens=50,
        )
        second = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="cache me",
            estimated_tokens=50,
        )

    assert first == mock_text
    assert second == mock_text
    assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_call_llm_fallback_on_error(router):
    call_count = 0

    async def mock_provider(model, prompt, system_prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Primary model down")
        return ("fallback response", 0.001)

    with patch.object(router, "_call_provider", side_effect=mock_provider):
        result = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="test",
            estimated_tokens=100,
        )
    if len(TASK_MODEL_MAP[TaskType.ROUTINE]) > 1 or settings.OPENROUTER_API_KEY:
        assert result == "fallback response"
        assert call_count == 2
    else:
        assert result is None
        assert call_count == 1


@pytest.mark.asyncio
async def test_call_llm_all_fail(router):
    async def always_fail(model, prompt, system_prompt):
        raise ConnectionError("down")

    with patch.object(router, "_call_provider", side_effect=always_fail):
        result = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="test",
            estimated_tokens=100,
        )
    assert result is None
