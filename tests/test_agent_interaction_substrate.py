import pytest

from agents.agent_registry import AgentRegistry
from agents.base_agent import BaseAgent, TaskResult
from modules.agent_event_bus import AgentEventBus


class HelperAgent(BaseAgent):
    NEEDS = {"default": ["memory", "quality_review"]}

    def __init__(self, name="helper_agent", caps=None, **kwargs):
        super().__init__(name=name, description="helper", **kwargs)
        self._caps = caps or ["helper_cap"]

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        return TaskResult(success=True, output={"task_type": task_type, "requested_by": kwargs.get("__requested_by")})


class OwnerAgent(BaseAgent):
    NEEDS = {"owner_cap": ["helper_cap", "quality_review"]}

    def __init__(self, name="owner_agent", caps=None, **kwargs):
        super().__init__(name=name, description="owner", **kwargs)
        self._caps = caps or ["owner_cap"]

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        delegated = await self.ask("helper_cap", topic="abc")
        return TaskResult(
            success=True,
            output={
                "delegated": bool(delegated and delegated.success),
                "helper_requested_by": getattr(delegated, "output", {}).get("requested_by") if delegated else None,
            },
        )


@pytest.mark.asyncio
async def test_registry_register_binds_registry_and_event_bus():
    reg = AgentRegistry()
    agent = OwnerAgent()
    reg.register(agent)
    assert agent.registry is reg
    assert getattr(agent, "_registry", None) is reg
    assert reg.get_event_bus() is not None


def test_base_agent_declared_needs():
    owner = OwnerAgent()
    assert owner.get_declared_needs("owner_cap") == ["helper_cap", "quality_review"]


@pytest.mark.asyncio
async def test_base_agent_ask_dispatches_through_registry():
    reg = AgentRegistry()
    owner = OwnerAgent()
    helper = HelperAgent()
    reg.register(owner)
    reg.register(helper)
    result = await reg.dispatch("owner_cap")
    assert result is not None
    assert result.success is True
    assert result.output["delegated"] is True
    assert result.output["helper_requested_by"] == "owner_agent"


@pytest.mark.asyncio
async def test_agent_event_bus_records_handoff():
    reg = AgentRegistry()
    owner = OwnerAgent()
    helper = HelperAgent()
    reg.register(owner)
    reg.register(helper)
    await reg.dispatch("owner_cap")
    events = reg.get_recent_agent_events(limit=10)
    assert any(e.get("event") == "agent_ask" for e in events)
    ask = next(e for e in events if e.get("event") == "agent_ask")
    assert ask["source_agent"] == "owner_agent"
    assert ask["data"]["capability"] == "helper_cap"


@pytest.mark.asyncio
async def test_agent_event_bus_persists_events_in_sqlite(tmp_path):
    bus = AgentEventBus(sqlite_path=str(tmp_path / "agent_events.db"))
    await bus.emit("agent_ask", {"capability": "helper_cap"}, source_agent="owner_agent")
    await bus.emit("dispatch_complete", {"capability": "helper_cap"}, source_agent="helper_agent")

    recent = bus.recent(limit=10)
    assert len(recent) == 2
    assert recent[0]["event"] == "agent_ask"
    assert recent[1]["event"] == "dispatch_complete"

    bus.clear()
    assert bus.recent(limit=10) == []
