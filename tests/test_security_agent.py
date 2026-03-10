"""Тесты SecurityAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import TaskResult


class TestSecurityAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.security_agent import SecurityAgent
        return SecurityAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "security_agent"
        assert "security" in agent.capabilities
        assert "key_rotation" in agent.capabilities

    @pytest.mark.asyncio
    async def test_audit_keys(self, agent):
        result = await agent.audit_keys()
        assert result.success is True
        assert result.output is not None
        assert result.metadata["security_runtime_profile"]["operation"] == "audit_keys"

    @pytest.mark.asyncio
    async def test_scan_vulnerabilities(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="No critical vulnerabilities found")
        result = await agent.scan_vulnerabilities()
        assert result.success is True
        assert result.metadata["security_runtime_profile"]["operation"] == "scan_vulnerabilities"

    @pytest.mark.asyncio
    async def test_rotate_key(self, agent):
        result = await agent.rotate_key("test_service")
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        result = await agent.execute_task("security")
        assert result.success is True
