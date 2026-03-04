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
        assert core.classify_step("Сканировать тренды Google") == "trend_scan"

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
        result = await core.execute_task("orchestrate", step="Сканировать тренды рынка")
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


class TestVITOCoreProductPipeline:
    @pytest.mark.asyncio
    async def test_product_pipeline_prepares_cross_agent_package(self):
        registry = AgentRegistry()

        class DummyRegistry:
            async def dispatch(self, task_type, **kwargs):
                if task_type == "niche_research":
                    return TaskResult(success=True, output="AI planners")
                if task_type == "research":
                    return TaskResult(success=True, output="research report")
                if task_type == "competitor_analysis":
                    return TaskResult(success=True, output="competitors")
                if task_type == "listing_seo_pack":
                    return TaskResult(success=True, output={"seo_score": 90})
                if task_type == "product_turnkey":
                    return TaskResult(
                        success=True,
                        output={
                            "topic": "AI planners",
                            "files": {
                                "pdf_path": "/tmp/a.pdf",
                                "cover_path": "/tmp/c.png",
                                "thumb_path": "/tmp/t.png",
                            },
                            "listing": {
                                "title": "AI planners",
                                "short_description": "short",
                                "category": "Programming",
                                "tags": ["ai", "planner"],
                                "seo_title": "AI planners",
                                "seo_description": "desc",
                            },
                        },
                    )
                if task_type in {"legal", "marketing_strategy", "campaign_plan", "listing_create"}:
                    return TaskResult(success=True, output={"url": "https://example.com/item"})
                return TaskResult(success=True, output={})

        core = VITOCore(registry=DummyRegistry())
        result = await core.execute_task("product_pipeline", topic="AI planners", platform="gumroad", auto_publish=False)
        assert result.success is True
        assert "publish_pack" in result.output
