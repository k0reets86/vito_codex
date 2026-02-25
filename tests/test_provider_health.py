from datetime import datetime, timedelta, timezone

from modules.provider_health import ProviderHealth


def test_provider_health_summary_detects_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rep = ProviderHealth().summary(rotation_days_max=90)
    assert "overall_status" in rep
    assert isinstance(rep.get("providers"), list)
    assert rep["missing_provider_count"] >= 1


def test_provider_health_rotation_due(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    old_dt = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    monkeypatch.setenv("OPENAI_API_KEY_ROTATED_AT", old_dt)
    rep = ProviderHealth().summary(rotation_days_max=90)
    openai = next((p for p in rep["providers"] if p["provider"] == "openai"), None)
    assert openai is not None
    assert openai["rotation_due"] is True
    assert rep["stale_provider_count"] >= 1
