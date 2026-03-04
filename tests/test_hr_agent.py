"""Тесты HRAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestHRAgent:
    @pytest.fixture
    def mock_registry(self):
        registry = MagicMock()
        registry.get_all_statuses = MagicMock(return_value=[
            {"name": "agent1", "status": "idle", "tasks_completed": 10, "tasks_failed": 2, "total_cost": 0.5},
            {"name": "agent2", "status": "idle", "tasks_completed": 5, "tasks_failed": 0, "total_cost": 0.2},
        ])
        return registry

    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms, mock_registry):
        from agents.hr_agent import HRAgent
        a = HRAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )
        a.registry = mock_registry
        return a

    def test_init(self, agent):
        assert agent.name == "hr_agent"
        assert "hr" in agent.capabilities
        assert "performance_evaluation" in agent.capabilities

    @pytest.mark.asyncio
    async def test_evaluate_performance(self, agent):
        result = await agent.evaluate_performance("agent1")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_agent_ranking(self, agent):
        result = await agent.agent_ranking()
        assert result.success is True
        assert isinstance(result.output, list)

    @pytest.mark.asyncio
    async def test_suggest_improvements(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Suggestions: optimize agent1...")
        result = await agent.suggest_improvements()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        result = await agent.execute_task("hr")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_suggest_improvements_local_fallback(self, agent):
        agent.llm_router = None
        result = await agent.suggest_improvements()
        assert result.success is True
