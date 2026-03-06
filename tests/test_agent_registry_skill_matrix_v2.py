import pytest

from agents.agent_registry import AgentRegistry
from agents.base_agent import BaseAgent, TaskResult


class _DummyAgent(BaseAgent):
    @property
    def capabilities(self):
        return ["research", "market_analysis"]

    async def execute_task(self, task_type: str, **kwargs):
        return TaskResult(success=True, output={"status": "ok"})


@pytest.mark.asyncio
async def test_agent_registry_skill_matrix_v2():
    reg = AgentRegistry()
    reg.register(_DummyAgent(name="research_agent", description="test"))
    rows = reg.get_skill_matrix_v2()
    assert len(rows) == 1
    assert rows[0]["agent"] == "research_agent"
    assert rows[0]["valid"] is True
    assert "sources" in rows[0]["required_evidence"]
    assert "research_report" in rows[0]["owned_outcomes"]
