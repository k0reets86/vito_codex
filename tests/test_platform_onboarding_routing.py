from unittest.mock import AsyncMock, MagicMock

import pytest

from conversation_engine import ConversationEngine
from agents.vito_core import VITOCore
from agents.base_agent import TaskResult


@pytest.fixture
def engine(mock_llm_router, mock_memory):
    return ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)


@pytest.mark.asyncio
async def test_dispatch_action_learn_service_uses_research_platform(mock_llm_router, mock_memory):
    registry = MagicMock()
    registry.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": {"id": "patreon"}})())
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
    msg = await engine._dispatch_action("learn_service", {"service": "patreon"})
    registry.dispatch.assert_awaited_once()
    assert registry.dispatch.await_args.args[0] == "research_platform"
    assert "patreon" in msg.lower()


@pytest.mark.asyncio
async def test_dispatch_action_onboard_platform(mock_llm_router, mock_memory):
    registry = MagicMock()
    registry.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": {"status": "active", "platform_id": "patreon"}})())
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
    msg = await engine._dispatch_action("onboard_platform", {"platform_name": "patreon"})
    assert registry.dispatch.await_args.args[0] == "onboard_platform"
    assert "platform_id=patreon" in msg


@pytest.mark.asyncio
async def test_handle_system_action_onboard_platform_requires_confirmation_when_not_autonomy_max(engine, monkeypatch):
    monkeypatch.setattr("conversation_engine.settings.AUTONOMY_MAX_MODE", False, raising=False)
    result = await engine._handle_system_action("подключи платформу patreon")
    assert result["intent"] == "system_action"
    assert result["actions"][0]["action"] == "onboard_platform"
    assert result["needs_confirmation"] is True


@pytest.mark.asyncio
async def test_vitocore_learn_service_delegates_to_onboarding():
    core = VITOCore(registry=None, llm_router=None, memory=None, finance=None, comms=None, skill_registry=None)

    class _Reg:
        def get(self, name):
            return object() if name == "platform_onboarding_agent" else None

        async def dispatch(self, task_type: str, **kwargs):
            return TaskResult(success=True, output={"id": "patreon"})

    core.registry = _Reg()
    result = await core.learn_service("patreon")
    assert result.success is True
    assert result.output["id"] == "patreon"
