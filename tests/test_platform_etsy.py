import pytest
from unittest.mock import AsyncMock

from platforms.etsy import EtsyPlatform


@pytest.mark.asyncio
async def test_etsy_pkce_start_generates_auth_url(tmp_path, monkeypatch):
    monkeypatch.setattr("platforms.etsy.PROJECT_ROOT", tmp_path, raising=False)
    etsy = EtsyPlatform()
    etsy._mode = "api"
    etsy._keystring = "etsy_key"
    etsy._state_path = tmp_path / "runtime" / "etsy_oauth_state.json"
    out = await etsy.start_oauth2_pkce()
    assert "auth_url" in out
    assert "code_challenge_method=S256" in out["auth_url"]
    assert out.get("state", "").startswith("vito_etsy_")
    assert etsy._state_path.exists()


@pytest.mark.asyncio
async def test_etsy_complete_oauth2_persists_tokens(tmp_path):
    etsy = EtsyPlatform()
    etsy._mode = "api"
    etsy._state_path = tmp_path / "runtime" / "etsy_oauth_state.json"
    etsy._keystring = "etsy_key"
    etsy._code_verifier = "verifier123"
    etsy._exchange_token = AsyncMock(return_value={"access_token": "acc", "refresh_token": "ref"})
    ok = await etsy.complete_oauth2("auth-code")
    assert ok is True
    assert etsy._oauth_token == "acc"
    assert etsy._refresh_token == "ref"
    assert etsy._state_path.exists()


@pytest.mark.asyncio
async def test_etsy_publish_returns_needs_oauth_with_auth_url():
    etsy = EtsyPlatform()
    etsy._mode = "api"
    etsy._oauth_token = ""
    etsy.start_oauth2_pkce = AsyncMock(return_value={"auth_url": "https://www.etsy.com/oauth/connect?x=1", "redirect_uri": "http://localhost/cb"})
    out = await etsy.publish({"title": "x", "description": "y"})
    assert out.get("status") == "needs_oauth"
    assert out.get("auth_url", "").startswith("https://www.etsy.com/oauth/connect")


@pytest.mark.asyncio
async def test_etsy_publish_refreshes_and_retries_on_401():
    etsy = EtsyPlatform()
    etsy._mode = "api"
    etsy._oauth_token = "old-token"
    etsy._refresh_token = "refresh-token"
    etsy._shop_id = "1234"
    etsy.refresh_oauth_token = AsyncMock(return_value=True)
    etsy._post_listing = AsyncMock(side_effect=[(401, {"error": "unauthorized"}), (201, {"listing_id": 999})])
    out = await etsy.publish({"title": "T", "description": "D", "price": 5, "quantity": 1, "taxonomy_id": 1, "tags": []})
    assert out.get("status") == "created"
    assert str(out.get("listing_id")) == "999"
    assert etsy.refresh_oauth_token.await_count == 1


@pytest.mark.asyncio
async def test_etsy_publish_browser_mode_requires_storage_state(tmp_path):
    etsy = EtsyPlatform()
    etsy._mode = "browser_only"
    etsy._storage_state_path = tmp_path / "missing_etsy_state.json"
    out = await etsy.publish({"title": "Browser listing", "description": "x"})
    assert out.get("status") == "needs_browser_login"
