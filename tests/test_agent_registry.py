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


class FakeBadPublishAgent(BaseAgent):
    def __init__(self, name, caps, **kwargs):
        super().__init__(name=name, description=f"Fake bad {name}", **kwargs)
        self._caps = caps

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        # Contract-invalid: published status without evidence fields.
        return TaskResult(success=True, output={"status": "published", "platform": "threads"})


class FakeHelperAgent(BaseAgent):
    def __init__(self, name, caps, **kwargs):
        super().__init__(name=name, description=f"Fake helper {name}", **kwargs)
        self._caps = caps

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        return TaskResult(success=True, output={"helper": self.name, "task": task_type})


class FakeVerifierAgent(BaseAgent):
    def __init__(self, name, caps, approved=True, **kwargs):
        super().__init__(name=name, description=f"Fake verifier {name}", **kwargs)
        self._caps = caps
        self._approved = approved

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        return TaskResult(success=True, output={"approved": self._approved, "score": 9 if self._approved else 3})


class FakeOwnerOrchestratingAgent(BaseAgent):
    def __init__(self, name, caps, **kwargs):
        super().__init__(name=name, description=f"Fake owner {name}", **kwargs)
        self._caps = caps

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    def build_task_orchestration(self, task_type: str, **kwargs) -> dict:
        return {
            "resources": ["memory", "llm_router"],
            "delegations": ["helper_cap"],
            "verify_with": "quality_review",
        }

    def consume_delegation_results(self, task_type: str, task_kwargs: dict, delegation_results: list[dict]) -> dict:
        merged = dict(task_kwargs)
        merged["delegated"] = delegation_results
        return merged

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        delegated = kwargs.get("delegated", [])
        return TaskResult(success=True, output={"status": "ok", "delegations_seen": len(delegated)})


class FakeMemoryAwareAgent(BaseAgent):
    def __init__(self, name, caps, **kwargs):
        super().__init__(name=name, description=f"Fake memory aware {name}", **kwargs)
        self._caps = caps

    @property
    def capabilities(self) -> list[str]:
        return self._caps

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        return TaskResult(
            success=True,
            output={
                "status": "ok",
                "contract_agent": (kwargs.get("__agent_contract") or {}).get("agent"),
                "memory_agent": (kwargs.get("__agent_memory_context") or {}).get("agent"),
            },
        )


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
    async def test_dispatch_marks_contract_invalid_as_failure(self):
        registry = AgentRegistry()
        agent = FakeBadPublishAgent("bad_pub", ["publish"])
        registry.register(agent)
        result = await registry.dispatch("publish")
        assert result is not None
        assert result.success is False
        assert "contract_invalid" in (result.error or "")

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

    @pytest.mark.asyncio
    async def test_dispatch_owner_orchestration_with_delegation_and_verification(self):
        registry = AgentRegistry()
        owner = FakeOwnerOrchestratingAgent("owner", ["main_cap"])
        helper = FakeHelperAgent("helper", ["helper_cap"])
        verifier = FakeVerifierAgent("judge", ["quality_review"], approved=True)
        registry.register(owner)
        registry.register(helper)
        registry.register(verifier)

        result = await registry.dispatch("main_cap")
        assert result is not None
        assert result.success is True
        assert isinstance(result.output, dict)
        assert result.output.get("delegations_seen") == 1
        assert isinstance(result.metadata, dict)
        assert result.metadata.get("responsible_agent") == "owner"
        assert isinstance(result.metadata.get("verification"), dict)
        assert result.metadata["verification"].get("approved") is True

    @pytest.mark.asyncio
    async def test_dispatch_owner_orchestration_verification_rejects(self):
        registry = AgentRegistry()
        owner = FakeOwnerOrchestratingAgent("owner", ["main_cap"])
        helper = FakeHelperAgent("helper", ["helper_cap"])
        verifier = FakeVerifierAgent("judge", ["quality_review"], approved=False)
        registry.register(owner)
        registry.register(helper)
        registry.register(verifier)

        result = await registry.dispatch("main_cap")
        assert result is not None
        assert result.success is False
        assert "verification_rejected:quality_review" in (result.error or "")


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

    @pytest.mark.asyncio
    async def test_dispatch_injects_contract_and_memory_context(self):
        class _Memory:
            def get_agent_memory_context(self, agent_name, task_type="", limit=5):
                return {"agent": agent_name, "task_type": task_type, "limit": limit}

        registry = AgentRegistry()
        agent = FakeMemoryAwareAgent("memory_agent", ["research"], memory=_Memory())
        registry.register(agent)
        result = await registry.dispatch("research")
        assert result.success is True
        assert result.output["contract_agent"] == "memory_agent"
        assert result.output["memory_agent"] == "memory_agent"

    def test_get_all_statuses(self):
        registry = AgentRegistry()
        a1 = FakeAgent("a1", ["cap1"])
        registry.register(a1)
        statuses = registry.get_all_statuses()
        assert len(statuses) == 1
        assert statuses[0]["name"] == "a1"
        assert "role" in statuses[0]
        assert "workflow_roles" in statuses[0]

    def test_get_workflow_map(self):
        registry = AgentRegistry()
        registry.register(FakeAgent("research_agent", ["research"]))
        workflow_map = registry.get_workflow_map()
        assert "research_pipeline" in workflow_map
        assert "research_agent" in workflow_map["research_pipeline"]["lead"]
