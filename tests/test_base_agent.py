"""Тесты BaseAgent — 9 тестов."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from agents.base_agent import BaseAgent, TaskResult, AgentStatus


class ConcreteAgent(BaseAgent):
    """Конкретная реализация для тестов."""

    @property
    def capabilities(self) -> list[str]:
        return ["test_cap", "another_cap"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        return TaskResult(success=True, output="done", cost_usd=0.01)


class TestBaseAgentAbstract:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            BaseAgent(name="test", description="test")

    def test_concrete_instantiation(self):
        agent = ConcreteAgent(name="test", description="Test agent")
        assert agent.name == "test"
        assert agent.description == "Test agent"


class TestBaseAgentInit:
    def test_init_with_dependencies(self, mock_llm_router, mock_memory, mock_finance):
        agent = ConcreteAgent(
            name="test",
            description="Test",
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
        )
        assert agent.llm_router is mock_llm_router
        assert agent.memory is mock_memory
        assert agent.finance is mock_finance

    def test_init_default_status(self):
        agent = ConcreteAgent(name="test", description="Test")
        assert agent._status == AgentStatus.STOPPED
        assert agent._tasks_completed == 0
        assert agent._tasks_failed == 0
        assert agent._total_cost == 0.0


class TestBaseAgentExecute:
    @pytest.mark.asyncio
    async def test_execute_task(self):
        agent = ConcreteAgent(name="test", description="Test")
        result = await agent.execute_task("test_cap")
        assert result.success is True
        assert result.output == "done"


class TestBaseAgentLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        agent = ConcreteAgent(name="test", description="Test")
        await agent.start()
        assert agent._status == AgentStatus.IDLE
        assert agent._started_at is not None
        await agent.stop()
        assert agent._status == AgentStatus.STOPPED


class TestBaseAgentStatus:
    @pytest.mark.asyncio
    async def test_get_status(self):
        agent = ConcreteAgent(name="test", description="Test")
        await agent.start()
        status = agent.get_status()
        assert status["name"] == "test"
        assert status["status"] == "idle"
        assert status["capabilities"] == ["test_cap", "another_cap"]


class TestBaseAgentNotify:
    @pytest.mark.asyncio
    async def test_notify_with_comms(self, mock_comms):
        agent = ConcreteAgent(name="test", description="Test", comms=mock_comms)
        await agent._notify("hello")
        mock_comms.send_message.assert_called_once_with("[test] hello")

    @pytest.mark.asyncio
    async def test_notify_without_comms(self):
        agent = ConcreteAgent(name="test", description="Test")
        await agent._notify("hello")  # No error


class TestBaseAgentExpenseAndBudget:
    def test_record_expense(self, mock_finance):
        agent = ConcreteAgent(name="test", description="Test", finance=mock_finance)
        agent._record_expense(0.05, "test expense")
        mock_finance.record_expense.assert_called_once()
        assert agent._total_cost == 0.05

    def test_check_budget(self, mock_finance):
        mock_finance.check_expense.return_value = {"allowed": True, "action": "auto", "reason": "ok"}
        agent = ConcreteAgent(name="test", description="Test", finance=mock_finance)
        result = agent._check_budget(1.0)
        assert result["allowed"] is True


class TestTaskResult:
    def test_task_result_defaults(self):
        r = TaskResult(success=True)
        assert r.output is None
        assert r.error is None
        assert r.cost_usd == 0.0
        assert r.duration_ms == 0
        assert r.metadata == {}

    def test_task_result_full(self):
        r = TaskResult(success=False, error="fail", cost_usd=1.5, duration_ms=500)
        assert r.success is False
        assert r.error == "fail"
