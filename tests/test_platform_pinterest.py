import pytest

from platforms.pinterest import PinterestPlatform


@pytest.mark.asyncio
async def test_pinterest_publish_dry_run_prepared():
    p = PinterestPlatform()
    out = await p.publish({"dry_run": True, "title": "Test pin"})
    assert out["platform"] == "pinterest"
    assert out["status"] == "prepared"
    assert out.get("dry_run") is True


@pytest.mark.asyncio
async def test_pinterest_publish_browser_requires_storage(monkeypatch, tmp_path):
    p = PinterestPlatform()
    p._mode = "browser"
    p._storage_state_path = tmp_path / "missing.json"
    out = await p.publish({"dry_run": False, "title": "Test pin"})
    assert out["platform"] == "pinterest"
    assert out["status"] == "needs_browser_login"
