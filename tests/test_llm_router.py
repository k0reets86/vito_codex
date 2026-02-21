"""Тесты llm_router.py."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def test_model_registry_has_all_models():
    expected = {"claude-sonnet", "claude-opus", "claude-haiku", "gpt-o3", "perplexity"}
    assert set(MODEL_REGISTRY.keys()) == expected


def test_task_model_map_has_all_types():
    for task_type in TaskType:
        assert task_type in TASK_MODEL_MAP
        assert len(TASK_MODEL_MAP[task_type]) >= 2  # основная + fallback


def test_model_config_fields():
    m = MODEL_REGISTRY["claude-sonnet"]
    assert m.provider == "anthropic"
    assert m.cost_per_1k_input > 0
    assert m.cost_per_1k_output > 0
    assert m.max_tokens > 0


def test_select_model_content():
    router = LLMRouter()
    result = router.select_model(TaskType.CONTENT, estimated_tokens=1000)
    assert isinstance(result, RouteResult)
    assert result.model.provider == "anthropic"
    assert "sonnet" in result.model.model_id.lower()
    assert result.estimated_cost_usd > 0


def test_select_model_strategy():
    router = LLMRouter()
    result = router.select_model(TaskType.STRATEGY)
    assert "opus" in result.model.model_id.lower()


def test_select_model_code():
    router = LLMRouter()
    result = router.select_model(TaskType.CODE)
    assert result.model.provider == "openai"


def test_select_model_research():
    router = LLMRouter()
    result = router.select_model(TaskType.RESEARCH)
    assert result.model.provider == "perplexity"


def test_select_model_routine():
    router = LLMRouter()
    result = router.select_model(TaskType.ROUTINE)
    assert "haiku" in result.model.model_id.lower()


def test_select_model_needs_approval_high_cost():
    router = LLMRouter()
    result = router.select_model(TaskType.STRATEGY, estimated_tokens=100000)
    assert result.needs_approval is True


def test_select_model_no_approval_low_cost():
    router = LLMRouter()
    result = router.select_model(TaskType.ROUTINE, estimated_tokens=100)
    assert result.needs_approval is False


def test_daily_spend_tracking():
    router = LLMRouter()
    assert router.get_daily_spend() == 0.0


def test_check_daily_limit_ok():
    router = LLMRouter()
    assert router.check_daily_limit() is True


def test_check_daily_limit_exceeded():
    router = LLMRouter()
    router._daily_spend = 999.0
    assert router.check_daily_limit() is False


@pytest.mark.asyncio
async def test_call_llm_returns_none_on_approval_needed():
    router = LLMRouter()
    # Очень дорогой запрос — needs_approval
    result = await router.call_llm(
        task_type=TaskType.STRATEGY,
        prompt="test",
        estimated_tokens=500000,
    )
    assert result is None


@pytest.mark.asyncio
async def test_call_llm_with_mock():
    router = LLMRouter()
    mock_response = "Test response from LLM"

    with patch.object(router, "_call_provider", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        result = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="test prompt",
            estimated_tokens=100,
        )
    assert result == mock_response
    assert router.get_daily_spend() > 0


@pytest.mark.asyncio
async def test_call_llm_fallback_on_error():
    router = LLMRouter()
    call_count = 0

    async def mock_provider(model, prompt, system_prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Primary model down")
        return "fallback response"

    with patch.object(router, "_call_provider", side_effect=mock_provider):
        result = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="test",
            estimated_tokens=100,
        )
    assert result == "fallback response"
    assert call_count == 2


@pytest.mark.asyncio
async def test_call_llm_all_fail():
    router = LLMRouter()

    async def always_fail(model, prompt, system_prompt):
        raise ConnectionError("down")

    with patch.object(router, "_call_provider", side_effect=always_fail):
        result = await router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt="test",
            estimated_tokens=100,
        )
    assert result is None
