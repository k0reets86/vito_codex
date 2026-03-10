from pathlib import Path

from config.settings import settings
import modules.browser_proxy_pool as proxy_pool
from modules.browser_proxy_pool import (
    configured_proxy_pool,
    report_proxy_result,
    select_proxy_for_service,
)


def test_configured_proxy_pool_parses_csv(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_PROXY_POOL", "http://a:1,http://b:2")
    assert configured_proxy_pool() == ["http://a:1", "http://b:2"]


def test_select_proxy_for_service_is_deterministic(monkeypatch):
    monkeypatch.setattr(proxy_pool, "_health_state_path", lambda: Path("/tmp/test_browser_proxy_pool_det.json"))
    monkeypatch.setattr(settings, "BROWSER_PROXY_POOL", "http://a:1,http://b:2,http://c:3")
    first = select_proxy_for_service("etsy", task_root_id="root-1", attempt=0)
    second = select_proxy_for_service("etsy", task_root_id="root-1", attempt=0)
    assert first == second
    assert first["server"].startswith("http://")


def test_failed_proxy_enters_cooldown_and_is_skipped(monkeypatch):
    monkeypatch.setattr(proxy_pool, "_health_state_path", lambda: Path("/tmp/test_browser_proxy_pool_fail.json"))
    monkeypatch.setattr(settings, "BROWSER_PROXY_POOL", "http://a:1,http://b:2")
    monkeypatch.setattr(settings, "BROWSER_PROXY_COOLDOWN_SEC", 60)
    report_proxy_result("http://a:1", ok=False, service="etsy", reason="timeout", cooldown_sec=60)
    selected = select_proxy_for_service("etsy", task_root_id="root-x", attempt=0)
    assert selected["server"] == "http://b:2"


def test_successful_proxy_reports_healthy(monkeypatch):
    monkeypatch.setattr(proxy_pool, "_health_state_path", lambda: Path("/tmp/test_browser_proxy_pool_ok.json"))
    monkeypatch.setattr(settings, "BROWSER_PROXY_POOL", "http://a:1")
    report_proxy_result("http://a:1", ok=True, service="etsy", reason="ok")
    selected = select_proxy_for_service("etsy", task_root_id="root-y", attempt=0)
    assert selected["server"] == "http://a:1"
    assert selected["healthy"] is True
