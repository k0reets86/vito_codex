"""Тесты VITOCore — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.vito_core import VITOCore
from agents.agent_registry import AgentRegistry
from agents.base_agent import TaskResult


class TestVITOCoreInit:
    def test_init(self):
        core = VITOCore()
        assert core.name == "vito_core"
        assert "orchestrate" in core.capabilities
        assert "classify" in core.capabilities
        assert "dispatch" in core.capabilities


class TestVITOCoreClassify:
    def test_classify_trend(self):
        core = VITOCore()
        assert core.classify_step("Исследовать тренды Google") == "trend_scan"

    def test_classify_content(self):
        core = VITOCore()
        assert core.classify_step("Create content for blog") == "content_creation"

    def test_classify_seo(self):
        core = VITOCore()
        assert core.classify_step("Провести SEO оптимизацию") == "seo"

    def test_classify_unknown(self):
        core = VITOCore()
        assert core.classify_step("do something random xyz") is None


class TestVITOCoreDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_to_agent(self):
        registry = AgentRegistry()
        mock_agent = MagicMock()
        mock_agent.name = "trend_scout"
        mock_agent.capabilities = ["trend_scan"]
        mock_agent.start = AsyncMock()  # Needed for lazy start
        mock_agent.execute_task = AsyncMock(
            return_value=TaskResult(success=True, output="trends found")
        )
        mock_agent._track_result = MagicMock()
        registry.register(mock_agent)

        core = VITOCore(registry=registry)
        result = await core.execute_task("orchestrate", step="Исследовать тренды рынка")
        assert result.success is True


class TestVITOCoreFallback:
    @pytest.mark.asyncio
    async def test_fallback_to_llm(self, mock_llm_router):
        mock_llm_router.call_llm = AsyncMock(return_value="LLM response")
        core = VITOCore(registry=AgentRegistry(), llm_router=mock_llm_router)
        result = await core.execute_task("orchestrate", step="something unknown xyz")
        assert result.success is True
        assert "LLM response" in result.output


class TestVITOCoreExecute:
    @pytest.mark.asyncio
    async def test_no_registry_no_llm(self):
        core = VITOCore()
        result = await core.execute_task("anything")
        assert result.success is False
        assert "Нет registry и llm_router" in result.error
