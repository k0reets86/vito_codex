from unittest.mock import AsyncMock

import pytest

from agents.platform_onboarding_agent import PlatformOnboardingAgent
from agents.base_agent import TaskResult
from modules import platform_registry as pr
from modules.platform_onboarding_records import PlatformOnboardingRecords


class _FakeRegistry:
    def __init__(self):
        self.calls = []

    async def dispatch(self, task_type: str, **kwargs):
        self.calls.append((task_type, kwargs))
        if task_type == "listing_create":
            return TaskResult(success=True, output={"id": "lst_1", "url": "https://example.com/listing/lst_1"})
        return TaskResult(success=True, output={})


@pytest.mark.asyncio
async def test_platform_onboarding_agent_onboard_registers_active_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "PROJECT_ROOT", tmp_path)
    reg = pr.PlatformRegistry(sqlite_path=str(tmp_path / "vito.db"))
    agent = PlatformOnboardingAgent(platform_registry=reg)
    agent.registry = _FakeRegistry()
    agent._phase1_research = AsyncMock(
        return_value={
            "id": "patreon",
            "name": "Patreon",
            "url": "https://www.patreon.com",
            "status": "researching",
            "overview": {"category": "commerce", "commission_percent": 8},
            "integration": {"browser": {"login_url": "https://www.patreon.com/login"}},
            "account": {},
            "products": {},
        }
    )
    agent._phase2_detect = AsyncMock(return_value={"method": "api", "auth_type": "oauth2"})
    agent._phase3_report = AsyncMock(return_value="auto_register")
    agent._phase4_account = AsyncMock(return_value={"success": True, "email_used": "owner@example.com", "username": "owner"})

    result = await agent.onboard("Patreon", "https://www.patreon.com")
    assert result["status"] == "active"
    assert result["platform_id"] == "patreon"
    saved = reg.get_profile("patreon")
    assert saved is not None
    assert saved["status"] == "active"
    assert saved["products"]["first_listing_id"] == "lst_1"


@pytest.mark.asyncio
async def test_platform_onboarding_agent_research_platform_task(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "PROJECT_ROOT", tmp_path)
    reg = pr.PlatformRegistry(sqlite_path=str(tmp_path / "vito.db"))
    agent = PlatformOnboardingAgent(platform_registry=reg)
    agent._phase1_research = AsyncMock(return_value={"id": "substack", "name": "Substack"})

    result = await agent.execute_task("research_platform", platform_name="Substack")
    assert result.success is True
    assert result.output["id"] == "substack"


@pytest.mark.asyncio
async def test_platform_onboarding_agent_persists_report_and_result(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "PROJECT_ROOT", tmp_path)
    reg = pr.PlatformRegistry(sqlite_path=str(tmp_path / "vito.db"))
    agent = PlatformOnboardingAgent(platform_registry=reg)
    agent.registry = _FakeRegistry()
    agent._records = PlatformOnboardingRecords(base_dir=tmp_path / "records")
    agent._phase1_research = AsyncMock(
        return_value={
            "id": "patreon",
            "name": "Patreon",
            "url": "https://www.patreon.com",
            "status": "researching",
            "overview": {"category": "subscription", "commission_percent": 8},
            "integration": {"browser": {"login_url": "https://www.patreon.com/login"}},
            "account": {},
            "products": {},
        }
    )
    agent._phase2_detect = AsyncMock(return_value={"method": "api", "auth_type": "oauth2"})
    agent._phase4_account = AsyncMock(return_value={"success": True, "email_used": "owner@example.com", "username": "owner"})
    agent._notify_wait = AsyncMock(return_value="2")

    result = await agent.onboard("Patreon", "https://www.patreon.com")
    assert result["status"] == "active"
    assert (tmp_path / "records" / "patreon_report.json").exists()
    assert (tmp_path / "records" / "patreon_result.json").exists()
