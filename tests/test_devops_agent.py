"""Тесты DevOpsAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import TaskResult


class TestDevOpsAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.devops_agent import DevOpsAgent
        return DevOpsAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "devops_agent"
        assert "health_check" in agent.capabilities
        assert "backup" in agent.capabilities
        assert "monitoring" in agent.capabilities

    @pytest.mark.asyncio
    async def test_health_check(self, agent):
        result = await agent.health_check()
        assert result.success is True
        assert "disk" in result.output or "health" in str(result.output).lower()

    @pytest.mark.asyncio
    async def test_backup(self, agent):
        with patch("shutil.copy2") as mock_copy, \
             patch("os.makedirs") as mock_makedirs, \
             patch("os.path.exists", return_value=True):
            result = await agent.backup()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_health_check(self, agent):
        with patch.object(agent, 'health_check', new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = TaskResult(success=True, output="all ok")
            result = await agent.execute_task("health_check")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_self_heal(self, agent):
        result = await agent.self_heal("high_memory_usage")
        assert isinstance(result, TaskResult)
