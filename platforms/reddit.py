"""RedditPlatform — lightweight Reddit publish adapter (SDK-pack step)."""

from __future__ import annotations

import aiohttp
import os
import re
from pathlib import Path

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from modules.execution_facts import ExecutionFacts
from platforms.base_platform import BasePlatform

logger = get_logger("reddit", agent="reddit")


class RedditPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="reddit", **kwargs)
        self._client_id = getattr(settings, "REDDIT_CLIENT_ID", "")
        self._client_secret = getattr(settings, "REDDIT_CLIENT_SECRET", "")
        self._username = getattr(settings, "REDDIT_USERNAME", "")
        self._password = getattr(settings, "REDDIT_PASSWORD", "")
        self._user_agent = getattr(settings, "REDDIT_USER_AGENT", "vito-bot/0.3")
        self._mode = str(getattr(settings, "REDDIT_MODE", "api") or "api").strip().lower()
        self._storage_state_path = Path(str(getattr(settings, "REDDIT_STORAGE_STATE_FILE", "runtime/reddit_storage_state.json") or "runtime/reddit_storage_state.json"))
        if not self._storage_state_path.is_absolute():
            self._storage_state_path = PROJECT_ROOT / self._storage_state_path
        self._token = ""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        if bool(getattr(settings, "REDDIT_API_DISABLED", False)) or self._mode == "browser_only":
            if self._storage_state_path.exists():
                try:
                    import json as _json
                    data = _json.loads(self._storage_state_path.read_text(encoding="utf-8"))
                    cookies = data.get("cookies") if isinstance(data, dict) else None
                    self._authenticated = bool(isinstance(cookies, list) and cookies)
                    return self._authenticated
                except Exception:
                    self._authenticated = False
                    return False
            self._authenticated = False
            return False
        if not (self._client_id and self._client_secret and self._username and self._password):
            self._authenticated = False
            return False
        try:
            session = await self._get_session()
            auth = aiohttp.BasicAuth(self._client_id, self._client_secret)
            data = {"grant_type": "password", "username": self._username, "password": self._password}
            headers = {"User-Agent": self._user_agent}
            async with session.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                payload = await resp.json()
                token = payload.get("access_token", "")
                self._token = token
                self._authenticated = bool(token)
                return self._authenticated
        except Exception as e:
            logger.warning(f"Reddit auth error: {e}", extra={"event": "reddit_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        if content.get("dry_run"):
            title = str(content.get("title", ""))
            subreddit = str(content.get("subreddit", "test"))
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"reddit dry_run subreddit={subreddit} title={title[:80]}",
                    evidence="dryrun:reddit",
                    source="reddit.publish",
                    evidence_dict={"platform": "reddit", "dry_run": True, "subreddit": subreddit, "title": title},
                )
            except Exception:
                pass
            return {"platform": "reddit", "status": "prepared", "dry_run": True, "subreddit": subreddit}

        if self._mode == "browser_only":
            return await self._publish_via_browser(content or {})

        if not self._authenticated:
            ok = await self.authenticate()
            if not ok:
                if self._storage_state_path.exists():
                    return await self._publish_via_browser(content or {})
                return {"platform": "reddit", "status": "not_authenticated"}

        subreddit = str(content.get("subreddit", "")).strip()
        title = str(content.get("title", "")).strip()
        body = str(content.get("text", "")).strip()
        link_url = str(content.get("url", "") or content.get("image_url", "")).strip()
        image_path = str(content.get("image_path", "")).strip()
        if not subreddit or not title:
            return {"platform": "reddit", "status": "error", "error": "subreddit/title required"}
        if image_path and not link_url:
            return {
                "platform": "reddit",
                "status": "error",
                "error": "image_path_not_supported_without_url; provide image_url/url for link post",
            }

        try:
            session = await self._get_session()
            headers = {"Authorization": f"Bearer {self._token}", "User-Agent": self._user_agent}
            if link_url:
                data = {"sr": subreddit, "title": title, "kind": "link", "url": link_url, "resubmit": "true", "api_type": "json"}
            else:
                data = {"sr": subreddit, "title": title, "kind": "self", "text": body, "resubmit": "true", "api_type": "json"}
            async with session.post(
                "https://oauth.reddit.com/api/submit",
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                payload = await resp.json()
                errs = (((payload or {}).get("json") or {}).get("errors") or [])
                if resp.status in (200, 201) and not errs:
                    try:
                        url = f"https://reddit.com/r/{subreddit}/new"
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"reddit subreddit={subreddit} title={title[:80]}",
                            evidence=url,
                            source="reddit.publish",
                            evidence_dict={"platform": "reddit", "subreddit": subreddit, "title": title},
                        )
                    except Exception:
                        pass
                    return {"platform": "reddit", "status": "published", "url": url}
                return {"platform": "reddit", "status": "error", "error": str(errs)[:300]}
        except Exception as e:
            return {"platform": "reddit", "status": "error", "error": str(e)}

    async def _publish_via_browser(self, content: dict) -> dict:
        if not self._storage_state_path.exists():
            return {
                "platform": "reddit",
                "status": "needs_browser_login",
                "error": "Reddit browser session required.",
                "storage_state": str(self._storage_state_path),
            }
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {"platform": "reddit", "status": "error", "error": "playwright_not_installed"}

        subreddit = str(content.get("subreddit", "")).strip() or "test"
        title = str(content.get("title", "")).strip()
        body = str(content.get("text", "")).strip()
        link_url = str(content.get("url", "") or content.get("image_url", "")).strip()
        if not title:
            return {"platform": "reddit", "status": "error", "error": "title required"}

        shot = str(PROJECT_ROOT / "runtime" / "reddit_browser_publish.png")
        browser = None
        context = None
        page = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=os.getenv("VITO_BROWSER_HEADLESS", "1").lower() not in {"0", "false", "no"},
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
                )
                context = await browser.new_context(
                    storage_state=str(self._storage_state_path),
                    viewport={"width": 1366, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                )
                page = await context.new_page()
                await page.goto(f"https://www.reddit.com/r/{subreddit}/submit/?type=TEXT", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(1200)
                current = (page.url or "").lower()
                body_text = (await page.text_content("body") or "").lower()
                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass
                if "blocked by network security" in body_text:
                    return {
                        "platform": "reddit",
                        "status": "blocked",
                        "error": "network_security_block",
                        "url": page.url,
                    }
                if any(x in current for x in ("/login", "reddit.com/login")):
                    return {
                        "platform": "reddit",
                        "status": "needs_browser_login",
                        "error": "Stored Reddit session expired.",
                        "storage_state": str(self._storage_state_path),
                    }
                title_selector = "textarea[name='title']"
                if not await page.locator(title_selector).count():
                    # Fallback for newer compose variants.
                    for candidate in ("textarea[placeholder*='Title']", "input[name='title']", "h3 + div textarea"):
                        if await page.locator(candidate).count():
                            title_selector = candidate
                            break
                await page.fill(title_selector, title[:300], timeout=2500)
                if link_url:
                    try:
                        await page.fill("input[name='url']", link_url, timeout=2500)
                    except Exception:
                        pass
                else:
                    try:
                        await page.fill("textarea[name='text']", body[:40000], timeout=2500)
                    except Exception:
                        pass
                posted = False
                for sel in ("button:has-text('Post')", "button[name='submit']", "button[type='submit']", "input[type='submit']"):
                    try:
                        btn = page.locator(sel)
                        if await btn.count():
                            await btn.first.click(timeout=2500)
                            posted = True
                            break
                    except Exception:
                        continue
                await page.wait_for_timeout(2500)
                post_url = str(page.url or "")
                if "/comments/" not in post_url:
                    try:
                        html_now = await page.content()
                        m = None
                        for pat in (
                            r'https://www\.reddit\.com/r/[^"\']+/comments/[a-z0-9]+/[^"\']*/',
                            r'/r/[^"\']+/comments/[a-z0-9]+/[^"\']*/',
                        ):
                            m = re.search(pat, html_now, re.IGNORECASE)
                            if m:
                                break
                        if m:
                            candidate = m.group(0)
                            post_url = candidate if candidate.startswith("http") else f"https://www.reddit.com{candidate}"
                    except Exception:
                        pass
                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass
                status = "published" if (posted and "/comments/" in post_url) else "prepared"
                try:
                    ExecutionFacts().record(
                        action="platform:publish",
                        status=status,
                        detail=f"reddit browser {status}",
                        evidence=post_url or f"https://old.reddit.com/r/{subreddit}/new/",
                        source="reddit.publish.browser",
                        evidence_dict={"platform": "reddit", "status": status, "url": post_url},
                    )
                except Exception:
                    pass
                return {
                    "platform": "reddit",
                    "status": status,
                    "url": post_url or f"https://old.reddit.com/r/{subreddit}/new/",
                    "mode": "browser_only",
                    "screenshot_path": shot,
                }
        except Exception as e:
            return {"platform": "reddit", "status": "error", "error": str(e), "screenshot_path": shot}
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

    async def get_analytics(self) -> dict:
        return {"platform": "reddit", "note": "basic adapter"}

    async def health_check(self) -> bool:
        return bool(self._client_id and self._client_secret)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
