from config.settings import settings
from modules.browser_proxy_pool import configured_proxy_pool, select_proxy_for_service


def test_configured_proxy_pool_parses_csv(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_PROXY_POOL", "http://a:1,http://b:2")
    assert configured_proxy_pool() == ["http://a:1", "http://b:2"]


def test_select_proxy_for_service_is_deterministic(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_PROXY_POOL", "http://a:1,http://b:2,http://c:3")
    first = select_proxy_for_service("etsy", task_root_id="root-1", attempt=0)
    second = select_proxy_for_service("etsy", task_root_id="root-1", attempt=0)
    assert first == second
    assert first["server"].startswith("http://")
