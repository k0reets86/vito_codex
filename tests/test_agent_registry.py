"""Тесты AgentRegistry — 8 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.agent_registry import AgentRegistry
from agents.base_agent import BaseAgent, TaskResult, AgentStatus


class FakeAgent(BaseAgent):
    def __init__(self, name, caps, **kwargs):
        super().__init__(name=name, description=f"Fake {name}", **kwargs)
        self._caps = caps

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        return TaskResult(success=True, output=f"{self.name} did {task_type}")


class TestRegistryRegister:
    def test_register(self):
        registry = AgentRegistry()
        agent = FakeAgent("a1", ["cap1"])
        registry.register(agent)
        assert registry.get("a1") is agent

    def test_register_multiple(self):
        registry = AgentRegistry()
        a1 = FakeAgent("a1", ["cap1"])
        a2 = FakeAgent("a2", ["cap2"])
        registry.register(a1)
        registry.register(a2)
        assert len(registry.agents) == 2


class TestRegistryUnregister:
    def test_unregister(self):
        registry = AgentRegistry()
        agent = FakeAgent("a1", ["cap1"])
        registry.register(agent)
        removed = registry.unregister("a1")
        assert removed is agent
        assert registry.get("a1") is None

    def test_unregister_nonexistent(self):
        registry = AgentRegistry()
        assert registry.unregister("nonexistent") is None


class TestRegistryFind:
    def test_find_by_capability(self):
        registry = AgentRegistry()
        a1 = FakeAgent("a1", ["seo", "content"])
        a2 = FakeAgent("a2", ["seo", "translate"])
        registry.register(a1)
        registry.register(a2)
        found = registry.find_by_capability("seo")
        assert len(found) == 2
        found_translate = registry.find_by_capability("translate")
        assert len(found_translate) == 1
        assert found_translate[0].name == "a2"


class TestRegistryDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        registry = AgentRegistry()
        agent = FakeAgent("a1", ["seo"])
        registry.register(agent)
        result = await registry.dispatch("seo")
        assert result.success is True
        assert "a1 did seo" in result.output

    @pytest.mark.asyncio
    async def test_dispatch_no_agent(self):
        registry = AgentRegistry()
        result = await registry.dispatch("nonexistent_cap")
        if result is None:
            assert True
        else:
            assert result.success is False

    @pytest.mark.asyncio
    async def test_dispatch_tooling_runner_fallback(self, tmp_path, monkeypatch):
        from modules.tooling_registry import ToolingRegistry
        from config import settings as settings_mod
        monkeypatch.setattr(settings_mod.settings, "SQLITE_PATH", str(tmp_path / "vito.db"))
        reg = ToolingRegistry(sqlite_path=str(tmp_path / "vito.db"))
        reg.upsert_adapter(
            adapter_key="demo_adapter",
            protocol="openapi",
            endpoint="https://example.com/openapi.json",
            schema={"openapi": "3.0.0", "paths": {}},
        )
        registry = AgentRegistry()
        result = await registry.dispatch("tooling:demo_adapter", dry_run=True, payload={"x": 1})
        assert result is not None
        assert result.success is True
        assert isinstance(result.output, dict)
        assert result.output.get("status") in {"dry_run", "prepared", "ok"}


class TestRegistryLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop_all(self):
        """start_all() now only starts CORE tier agents.
        Non-core agents start lazily on first dispatch."""
        registry = AgentRegistry()
        # Use core agent names so they start with start_all()
        a1 = FakeAgent("vito_core", ["cap1"])
        a2 = FakeAgent("devops_agent", ["cap2"])
        registry.register(a1)
        registry.register(a2)
        await registry.start_all()
        assert a1._status == AgentStatus.IDLE
        assert a2._status == AgentStatus.IDLE
        await registry.stop_all()
        assert a1._status == AgentStatus.STOPPED
        assert a2._status == AgentStatus.STOPPED

    @pytest.mark.asyncio
    async def test_lazy_start_on_dispatch(self):
        """Non-core agents start lazily when dispatched."""
        registry = AgentRegistry()
        agent = FakeAgent("test_agent", ["test_cap"])
        registry.register(agent)
        assert agent._status == AgentStatus.STOPPED
        await registry.dispatch("test_cap")
        assert agent._status == AgentStatus.IDLE  # started by lazy start

    def test_get_all_statuses(self):
        registry = AgentRegistry()
        a1 = FakeAgent("a1", ["cap1"])
        registry.register(a1)
        statuses = registry.get_all_statuses()
        assert len(statuses) == 1
        assert statuses[0]["name"] == "a1"
