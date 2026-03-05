"""EtsyPlatform — Etsy API v3 integration with OAuth2 PKCE write flow."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from modules.execution_facts import ExecutionFacts
from modules.listing_optimizer import optimize_listing_payload
from platforms.base_platform import BasePlatform

logger = get_logger("etsy", agent="etsy")
API_BASE = "https://openapi.etsy.com/v3"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"


class EtsyPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="etsy", **kwargs)
        self._keystring = settings.ETSY_KEYSTRING
        self._shared_secret = settings.ETSY_SHARED_SECRET
        self._oauth_token: str = settings.ETSY_OAUTH_ACCESS_TOKEN
        self._refresh_token: str = settings.ETSY_OAUTH_REFRESH_TOKEN
        self._shop_id: str = settings.ETSY_SHOP_ID
        self._redirect_uri: str = settings.ETSY_OAUTH_REDIRECT_URI
        self._mode: str = str(getattr(settings, "ETSY_MODE", "api") or "api").strip().lower()
        self._storage_state_path = Path(str(getattr(settings, "ETSY_STORAGE_STATE_FILE", "runtime/etsy_storage_state.json") or "runtime/etsy_storage_state.json"))
        if not self._storage_state_path.is_absolute():
            self._storage_state_path = PROJECT_ROOT / self._storage_state_path
        self._storage_state_backup_path = self._storage_state_path.with_suffix(".backup.json")
        self._code_verifier: str = ""
        self._session: aiohttp.ClientSession | None = None
        self._state_path = PROJECT_ROOT / "runtime" / "etsy_oauth_state.json"
        self._load_oauth_state()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self, write: bool = False) -> dict[str, str]:
        headers = {"x-api-key": self._keystring}
        if write and self._oauth_token:
            headers["Authorization"] = f"Bearer {self._oauth_token}"
        return headers

    def _load_oauth_state(self) -> None:
        try:
            if not self._state_path.exists():
                return
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._oauth_token = str(data.get("access_token") or self._oauth_token or "")
            self._refresh_token = str(data.get("refresh_token") or self._refresh_token or "")
            self._shop_id = str(data.get("shop_id") or self._shop_id or "")
            self._code_verifier = str(data.get("code_verifier") or self._code_verifier or "")
        except Exception:
            pass

    def _persist_oauth_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "access_token": self._oauth_token,
                "refresh_token": self._refresh_token,
                "shop_id": self._shop_id,
                "code_verifier": self._code_verifier,
            }
            self._state_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    async def authenticate(self) -> bool:
        """Verify API key via ping endpoint."""
        if self._mode in {"browser", "browser_only"}:
            return await self._authenticate_browser_mode()
        if not self._keystring:
            self._authenticated = False
            return False

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/openapi-ping",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                self._authenticated = resp.status == 200
                if self._authenticated:
                    logger.info("Etsy API key verified", extra={"event": "etsy_auth_ok"})
                else:
                    body = await resp.text()
                    logger.warning(
                        f"Etsy auth failed: {resp.status} {body[:200]}",
                        extra={"event": "etsy_auth_fail"},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Etsy auth error: {e}", exc_info=True)
            self._authenticated = False
            return False

    async def _authenticate_browser_mode(self) -> bool:
        if not self._storage_state_path.exists() and self._storage_state_backup_path.exists():
            try:
                self._storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                self._storage_state_path.write_text(
                    self._storage_state_backup_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                logger.info("Etsy storage_state restored from backup", extra={"event": "etsy_storage_restore_backup"})
            except Exception:
                pass
        if not self._storage_state_path.exists():
            self._authenticated = False
            return False
        try:
            raw = self._storage_state_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            cookies = data.get("cookies") if isinstance(data, dict) else None
            if isinstance(cookies, list) and len(cookies) > 0:
                try:
                    self._storage_state_backup_path.write_text(raw, encoding="utf-8")
                except Exception:
                    pass
                self._authenticated = True
                return True
        except Exception:
            self._authenticated = False
            return False
        self._authenticated = False
        return False

    async def _publish_via_browser(self, content: dict) -> dict:
        content = optimize_listing_payload("etsy", content or {})
        operation = str(content.get("operation") or "create").strip().lower()
        allow_existing_update = bool(content.get("allow_existing_update"))
        owner_edit_confirmed = bool(content.get("owner_edit_confirmed"))
        target_listing_id = str(content.get("target_listing_id") or "").strip()
        if bool(getattr(settings, "PUBLISH_CREATE_GUARD_ENABLED", True)):
            if operation in {"create", "new"} and allow_existing_update:
                return {
                    "platform": "etsy",
                    "status": "blocked",
                    "error": "create_mode_forbids_existing_update",
                }
            if allow_existing_update and not owner_edit_confirmed:
                return {
                    "platform": "etsy",
                    "status": "blocked",
                    "error": "existing_update_requires_explicit_owner_request",
                }
        if allow_existing_update and not target_listing_id:
            return {
                "platform": "etsy",
                "status": "blocked",
                "error": "existing_update_requires_target_listing_id",
            }
        if not self._storage_state_path.exists():
            return {
                "platform": "etsy",
                "status": "needs_browser_login",
                "error": "Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture",
                "storage_state": str(self._storage_state_path),
            }
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {"platform": "etsy", "status": "error", "error": "playwright_not_installed"}

        title = str(content.get("title") or "VITO Etsy Product").strip()
        description = str(content.get("description") or "").strip()
        price = str(content.get("price") or "5")
        tags = content.get("tags") or []
        shot = str(PROJECT_ROOT / "runtime" / "etsy_browser_publish.png")
        page_html = str(PROJECT_ROOT / "runtime" / "etsy_browser_publish.html")

        browser = None
        context = None
        page = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=os.getenv("VITO_BROWSER_HEADLESS", "1").lower() not in {"0", "false", "no"},
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context = await browser.new_context(
                    storage_state=str(self._storage_state_path),
                    viewport={"width": 1366, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                )
                page = await context.new_page()
                await page.goto("https://www.etsy.com/your/shops/me/tools/listings/create", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(2000)
                current = page.url.lower()
                if "/signin" in current or "/oauth" in current:
                    return {
                        "platform": "etsy",
                        "status": "needs_browser_login",
                        "error": "Stored Etsy session expired.",
                        "storage_state": str(self._storage_state_path),
                    }
                if "/listing/" in current and "/edit" in current:
                    if not allow_existing_update:
                        return {
                            "platform": "etsy",
                            "status": "blocked",
                            "error": "existing_listing_edit_detected_without_explicit_update",
                            "url": page.url,
                        }
                    if target_listing_id and f"/listing/{target_listing_id}" not in current:
                        return {
                            "platform": "etsy",
                            "status": "blocked",
                            "error": "existing_listing_mismatch_target",
                            "url": page.url,
                        }

                # Best-effort field fill; Etsy UI may vary by locale/account state.
                for sel in ("input[name='title']", "input[data-test-id='listing-title-input']", "input[id*='title']"):
                    try:
                        await page.fill(sel, title[:140])
                        break
                    except Exception:
                        continue
                for sel in ("textarea[name='description']", "textarea[id*='description']", "textarea"):
                    try:
                        await page.fill(sel, description[:5000])
                        break
                    except Exception:
                        continue
                for sel in ("input[name='price']", "input[id*='price']"):
                    try:
                        await page.fill(sel, price)
                        break
                    except Exception:
                        continue
                if tags:
                    tags_text = ", ".join(str(t)[:20] for t in tags[:13])
                    for sel in ("input[name='tags']", "input[id*='tag']"):
                        try:
                            await page.fill(sel, tags_text)
                            break
                        except Exception:
                            continue

                # Try draft/save actions if visible
                for txt in ("Save as draft", "Save and continue", "Save"):
                    try:
                        btn = page.get_by_role("button", name=txt)
                        if await btn.count():
                            await btn.first.click(timeout=2500)
                            await page.wait_for_timeout(1200)
                            break
                    except Exception:
                        continue

                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass
                try:
                    html = await page.content()
                    Path(page_html).parent.mkdir(parents=True, exist_ok=True)
                    Path(page_html).write_text(html or "", encoding="utf-8")
                except Exception:
                    pass

                listing_id = ""
                m = re.search(r"/listing/(\d+)", page.url)
                if m:
                    listing_id = m.group(1)
                if listing_id:
                    url = f"https://www.etsy.com/listing/{listing_id}"
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="created",
                            detail=f"etsy browser listing_id={listing_id}",
                            evidence=url,
                            source="etsy.publish.browser",
                            evidence_dict={"platform": "etsy", "listing_id": listing_id, "url": url},
                        )
                    except Exception:
                        pass
                    return {
                        "platform": "etsy",
                        "status": "created",
                        "listing_id": listing_id,
                        "url": url,
                        "mode": "browser_only",
                        "screenshot_path": shot,
                    }
                return {
                    "platform": "etsy",
                    "status": "prepared",
                    "mode": "browser_only",
                    "url": page.url,
                    "screenshot_path": shot,
                    "note": "Draft editor opened and fields filled; listing_id not detected yet.",
                }
        except Exception as e:
            return {"platform": "etsy", "status": "error", "error": str(e), "screenshot_path": shot}
        finally:
            try:
                if page is not None:
                    await page.close()
            except Exception:
                pass
            try:
                if context is not None:
                    await context.close()
            except Exception:
                pass
            try:
                if browser is not None:
                    await browser.close()
            except Exception:
                pass

    async def get_shop(self, shop_id: str = "") -> dict:
        """GET /v3/application/shops/{shop_id} — get shop info."""
        if not self._authenticated:
            await self.authenticate()
        if not self._authenticated:
            return {}

        sid = shop_id or self._shop_id
        if not sid:
            return {"error": "No shop_id configured"}

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/shops/{sid}",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def search_listings(self, keywords: str, limit: int = 25) -> list[dict]:
        """GET /v3/application/listings/active — search active listings."""
        if not self._authenticated:
            await self.authenticate()
        if not self._authenticated:
            return []

        try:
            session = await self._get_session()
            params = {"keywords": keywords, "limit": min(limit, 100)}
            async with session.get(
                f"{API_BASE}/application/listings/active",
                headers=self._headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    logger.info(
                        f"Etsy search '{keywords}': {len(results)} results",
                        extra={"event": "etsy_search_ok", "context": {"count": len(results)}},
                    )
                    return results
                return []
        except Exception as e:
            logger.error(f"Etsy search error: {e}", exc_info=True)
            return []

    async def get_listing(self, listing_id: int) -> dict:
        """GET /v3/application/listings/{listing_id}."""
        if not self._authenticated:
            await self.authenticate()

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/listings/{listing_id}",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def get_trending_keywords(self) -> list[dict]:
        """GET /v3/application/buyer-taxonomy/nodes — browse categories."""
        if not self._authenticated:
            await self.authenticate()

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/buyer-taxonomy/nodes",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("results", [])
                return []
        except Exception as e:
            logger.error(f"Etsy taxonomy error: {e}", exc_info=True)
            return []

    async def start_oauth2_pkce(self) -> dict[str, Any]:
        """Start OAuth2 PKCE flow and return authorization URL."""
        if not self._keystring:
            return {"error": "ETSY_KEYSTRING is missing"}

        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()

        self._code_verifier = code_verifier
        self._persist_oauth_state()

        scopes = "listings_w listings_r transactions_r shops_r"
        state = f"vito_etsy_{secrets.token_urlsafe(8)}"

        auth_url = (
            "https://www.etsy.com/oauth/connect"
            f"?response_type=code"
            f"&redirect_uri={quote(self._redirect_uri, safe='')}"
            f"&scope={quote(scopes, safe='')}"
            f"&client_id={self._keystring}"
            f"&state={state}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

        logger.info("Etsy OAuth2 PKCE flow started", extra={"event": "etsy_oauth_start"})
        return {
            "auth_url": auth_url,
            "state": state,
            "redirect_uri": self._redirect_uri,
            "note": "Open auth_url, then pass `code` from callback to complete_oauth2(code)",
        }

    async def _exchange_token(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            session = await self._get_session()
            async with session.post(
                TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                logger.warning(
                    f"Etsy token exchange failed: {resp.status} {body[:200]}",
                    extra={"event": "etsy_oauth_exchange_fail", "context": {"status": resp.status}},
                )
                return None
        except Exception as e:
            logger.error(f"Etsy token exchange error: {e}", extra={"event": "etsy_oauth_exchange_error"}, exc_info=True)
            return None

    async def complete_oauth2(self, auth_code: str, code_verifier: str = "") -> bool:
        """Exchange auth code for access/refresh token."""
        verifier = code_verifier or self._code_verifier
        if not verifier:
            logger.warning("No code_verifier for Etsy OAuth2", extra={"event": "etsy_oauth_no_verifier"})
            return False

        data = await self._exchange_token(
            {
                "grant_type": "authorization_code",
                "client_id": self._keystring,
                "redirect_uri": self._redirect_uri,
                "code": auth_code,
                "code_verifier": verifier,
            }
        )
        if not data:
            return False

        self._oauth_token = str(data.get("access_token") or "")
        self._refresh_token = str(data.get("refresh_token") or "")
        self._persist_oauth_state()
        logger.info("Etsy OAuth2 completed successfully", extra={"event": "etsy_oauth_ok"})
        return bool(self._oauth_token)

    async def refresh_oauth_token(self) -> bool:
        """Refresh OAuth2 token using refresh_token."""
        if not self._refresh_token:
            return False

        data = await self._exchange_token(
            {
                "grant_type": "refresh_token",
                "client_id": self._keystring,
                "refresh_token": self._refresh_token,
            }
        )
        if not data:
            return False

        self._oauth_token = str(data.get("access_token") or "")
        self._refresh_token = str(data.get("refresh_token") or self._refresh_token or "")
        self._persist_oauth_state()
        logger.info("Etsy OAuth2 refreshed", extra={"event": "etsy_oauth_refreshed"})
        return bool(self._oauth_token)

    async def oauth_status(self) -> dict[str, Any]:
        return {
            "has_keystring": bool(self._keystring),
            "has_access_token": bool(self._oauth_token),
            "has_refresh_token": bool(self._refresh_token),
            "shop_id": self._shop_id,
            "redirect_uri": self._redirect_uri,
        }

    async def _post_listing(self, listing_data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        session = await self._get_session()
        async with session.post(
            f"{API_BASE}/application/shops/{self._shop_id}/listings",
            headers={**self._headers(write=True), "Content-Type": "application/json"},
            json=listing_data,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.content_type and "json" in resp.content_type:
                body = await resp.json()
            else:
                body = {"error": (await resp.text())[:300]}
            return resp.status, body

    async def publish(self, content: dict) -> dict:
        """Create a draft listing (requires OAuth2 token for write)."""
        if content.get("dry_run"):
            title = content.get("title", "")
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"etsy dry_run title={str(title)[:80]}",
                    evidence="dryrun:etsy",
                    source="etsy.publish",
                    evidence_dict={"platform": "etsy", "dry_run": True, "title": title},
                )
            except Exception:
                pass
            return {
                "platform": "etsy",
                "status": "prepared",
                "dry_run": True,
                "title": title,
            }
        if self._mode in {"browser", "browser_only"}:
            return await self._publish_via_browser(content)

        if not self._oauth_token:
            logger.warning("Etsy publish requires OAuth2 token", extra={"event": "etsy_publish_no_oauth"})
            start = await self.start_oauth2_pkce()
            return {
                "platform": "etsy",
                "status": "needs_oauth",
                "error": "OAuth2 PKCE token required for write operations.",
                "auth_url": start.get("auth_url", ""),
                "redirect_uri": start.get("redirect_uri", self._redirect_uri),
            }

        if not self._shop_id:
            return {"platform": "etsy", "status": "error", "error": "No shop_id configured (ETSY_SHOP_ID)"}

        try:
            listing_data = {
                "title": content.get("title", ""),
                "description": content.get("description", ""),
                "price": content.get("price", 0),
                "quantity": content.get("quantity", 1),
                "taxonomy_id": content.get("taxonomy_id", 0),
                "tags": content.get("tags", []),
                "who_made": content.get("who_made", "i_did"),
                "when_made": content.get("when_made", "2020_2025"),
                "is_supply": content.get("is_supply", False),
                "type": "download",
                "state": "draft",
            }

            status_code, data = await self._post_listing(listing_data)
            if status_code == 401 and await self.refresh_oauth_token():
                status_code, data = await self._post_listing(listing_data)

            if status_code in (200, 201):
                listing_id = data.get("listing_id", "")
                listing_url = f"https://www.etsy.com/listing/{listing_id}" if listing_id else ""
                logger.info(
                    f"Etsy listing created: {listing_id}",
                    extra={"event": "etsy_publish_ok", "context": {"listing_id": listing_id}},
                )
                try:
                    ExecutionFacts().record(
                        action="platform:publish",
                        status="created",
                        detail=f"etsy listing_id={listing_id}",
                        evidence=listing_url,
                        source="etsy.publish",
                        evidence_dict={"platform": "etsy", "listing_id": listing_id, "url": listing_url},
                    )
                except Exception:
                    pass
                return {
                    "platform": "etsy",
                    "status": "created",
                    "listing_id": listing_id,
                    "url": listing_url,
                    "state": "draft",
                    "data": data,
                }

            error = data.get("error", str(status_code))
            logger.warning(f"Etsy publish failed: {error}", extra={"event": "etsy_publish_fail"})
            return {"platform": "etsy", "status": "error", "error": error}

        except Exception as e:
            logger.error(f"Etsy publish error: {e}", exc_info=True)
            return {"platform": "etsy", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """Get shop analytics (basic listing stats)."""
        if not self._shop_id:
            return {"platform": "etsy", "views": 0, "sales": 0, "revenue": 0.0}

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/shops/{self._shop_id}/listings/active",
                headers=self._headers(),
                params={"limit": 100},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    listings = data.get("results", [])
                    total_views = sum(l.get("views", 0) for l in listings)
                    total_favorites = sum(l.get("num_favorers", 0) for l in listings)
                    return {
                        "platform": "etsy",
                        "listings": len(listings),
                        "views": total_views,
                        "favorites": total_favorites,
                        "sales": 0,
                        "revenue": 0.0,
                    }
        except Exception as e:
            logger.error(f"Etsy analytics error: {e}", exc_info=True)

        return {"platform": "etsy", "views": 0, "sales": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
