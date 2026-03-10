import json
from unittest.mock import AsyncMock

import pytest

from agents.platform_onboarding_agent import PlatformOnboardingAgent
from scripts import platform_onboarding_validation as pov


@pytest.mark.asyncio
async def test_platform_onboarding_validation_reports_paths(monkeypatch, tmp_path):
    async def _fake_phase1(self, name, url):
        return {"id": "substack", "name": "Substack", "url": url, "overview": {}, "integration": {}}

    async def _fake_phase2(self, profile):
        return {"method": "api"}

    async def _fake_phase3(self, profile, integration):
        return "auto_register"

    monkeypatch.setattr(PlatformOnboardingAgent, "_phase1_research", _fake_phase1)
    monkeypatch.setattr(PlatformOnboardingAgent, "_phase2_detect", _fake_phase2)
    monkeypatch.setattr(PlatformOnboardingAgent, "_phase3_report", _fake_phase3)
    result = await pov.run_validation("Substack", "https://substack.com")
    assert result["ok"] is True
    assert result["platform_id"] == "substack"

