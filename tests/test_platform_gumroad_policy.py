import pytest

from platforms.gumroad import GumroadPlatform
import platforms.gumroad as gumroad_mod


@pytest.mark.asyncio
async def test_gumroad_existing_update_requires_explicit_target():
    p = GumroadPlatform()
    out = await p.publish(
        {
            "allow_existing_update": True,
            "owner_edit_confirmed": True,
            "name": "Any",
            "description": "x",
            "price": 1,
        }
    )
    assert out.get("status") == "blocked"
    assert out.get("error") in {
        "create_mode_forbids_existing_update",
        "existing_update_requires_target_product_id_or_slug",
    }
    await p.close()


@pytest.mark.asyncio
async def test_gumroad_existing_update_fallback_to_api_toggle(monkeypatch):
    p = GumroadPlatform()
    p._authenticated = True

    monkeypatch.setattr(gumroad_mod, "network_status", lambda *_args, **_kwargs: {"ok": True, "reason": ""})

    async def _fake_browser_fail(_content):
        return {"platform": "gumroad", "status": "error", "error": "browser_failed"}

    async def _fake_enable(product_id):
        return {"platform": "gumroad", "status": "published", "product_id": product_id}

    async def _fake_auth():
        return True

    async def _fake_cookie():
        return True

    monkeypatch.setattr(p, "_publish_via_browser", _fake_browser_fail)
    monkeypatch.setattr(p, "enable_product", _fake_enable)
    monkeypatch.setattr(p, "authenticate", _fake_auth)
    monkeypatch.setattr(p, "_ensure_session_cookie", _fake_cookie)

    out = await p.publish(
        {
            "operation": "update",
            "allow_existing_update": True,
            "owner_edit_confirmed": True,
            "target_product_id": "PID123",
            "name": "Any",
            "description": "x",
            "price": 1,
            "keep_unpublished": False,
        }
    )
    assert out.get("status") == "published"
    assert out.get("fallback") == "api_toggle_after_browser_failure"
    await p.close()
