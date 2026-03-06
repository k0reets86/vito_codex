"""TwitterPlatform — интеграция с X.com (Twitter) API v2.

OAuth 1.0a для постинга. Все ключи уже в .env.
"""

import hashlib
import hmac
import os
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from config.paths import PROJECT_ROOT
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("twitter", agent="twitter")

API_V2 = "https://api.twitter.com/2"
UPLOAD_API_V1 = "https://upload.twitter.com/1.1/media/upload.json"


class TwitterPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="twitter", **kwargs)
        self._mode = str(getattr(settings, "TWITTER_MODE", "api") or "api").strip().lower()
        self._consumer_key = settings.TWITTER_CONSUMER_KEY
        self._consumer_secret = settings.TWITTER_CONSUMER_SECRET
        self._access_token = settings.TWITTER_ACCESS_TOKEN
        self._access_secret = settings.TWITTER_ACCESS_SECRET
        self._bearer_token = settings.TWITTER_BEARER_TOKEN
        self._storage_state_path = Path(str(getattr(settings, "TWITTER_STORAGE_STATE_FILE", "runtime/twitter_storage_state.json") or "runtime/twitter_storage_state.json"))
        if not self._storage_state_path.is_absolute():
            self._storage_state_path = PROJECT_ROOT / self._storage_state_path
        self._session: aiohttp.ClientSession | None = None
        self._user_id: str = ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _oauth1_header(self, method: str, url: str, params: dict | None = None) -> str:
        """Generate OAuth 1.0a Authorization header."""
        oauth_params = {
            "oauth_consumer_key": self._consumer_key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self._access_token,
            "oauth_version": "1.0",
        }

        all_params = {**oauth_params}
        if params:
            all_params.update(params)

        # Create signature base string
        sorted_params = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(sorted_params, safe='')}"

        # Create signing key
        signing_key = f"{urllib.parse.quote(self._consumer_secret, safe='')}&{urllib.parse.quote(self._access_secret, safe='')}"

        # Generate signature
        signature = hmac.new(
            signing_key.encode(), base_string.encode(), hashlib.sha1
        ).digest()
        oauth_params["oauth_signature"] = urllib.parse.quote(
            __import__("base64").b64encode(signature).decode(), safe=""
        )

        # Build header
        auth_header = "OAuth " + ", ".join(
            f'{k}="{v}"' for k, v in sorted(oauth_params.items())
        )
        return auth_header

    async def authenticate(self) -> bool:
        """Verify credentials via GET /2/users/me."""
        if self._mode in {"browser", "browser_only"}:
            if not self._storage_state_path.exists():
                self._authenticated = False
                return False
            try:
                import json as _json
                data = _json.loads(self._storage_state_path.read_text(encoding="utf-8"))
                cookies = data.get("cookies") if isinstance(data, dict) else None
                self._authenticated = bool(isinstance(cookies, list) and cookies)
                return self._authenticated
            except Exception:
                self._authenticated = False
                return False
        if not all([self._consumer_key, self._consumer_secret, self._access_token, self._access_secret]):
            self._authenticated = False
            return False

        try:
            session = await self._get_session()
            url = f"{API_V2}/users/me"
            headers = {
                "Authorization": self._oauth1_header("GET", url),
            }
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("data", {})
                    self._user_id = user.get("id", "")
                    self._authenticated = True
                    logger.info(
                        f"Twitter auth OK: @{user.get('username', '?')}",
                        extra={"event": "twitter_auth_ok", "context": {"username": user.get("username")}},
                    )
                else:
                    body = await resp.text()
                    self._authenticated = False
                    logger.warning(
                        f"Twitter auth failed: {resp.status} {body[:200]}",
                        extra={"event": "twitter_auth_fail"},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Twitter auth error: {e}", exc_info=True)
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """POST /2/tweets — create a tweet.

        content: {text: str, reply_to: str (optional), media_ids: list (optional)}
        """
        if content.get("dry_run"):
            preview = (content.get("text", "") or "")[:280]
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"twitter dry_run preview_len={len(preview)}",
                    evidence="dryrun:twitter",
                    source="twitter.publish",
                    evidence_dict={"platform": "twitter", "dry_run": True, "text_preview": preview},
                )
            except Exception:
                pass
            return {
                "platform": "twitter",
                "status": "prepared",
                "dry_run": True,
                "text_preview": preview,
            }

        if self._mode in {"browser", "browser_only"}:
            return await self._publish_via_browser(content or {})

        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                if self._storage_state_path.exists():
                    return await self._publish_via_browser(content or {})
                return {"platform": "twitter", "status": "not_authenticated"}

        text = content.get("text", "")
        if not text:
            return {"platform": "twitter", "status": "error", "error": "No text provided"}

        # Twitter limit: 280 chars
        if len(text) > 280:
            text = text[:277] + "..."

        try:
            session = await self._get_session()
            url = f"{API_V2}/tweets"
            payload: dict[str, Any] = {"text": text}
            media_ids = list(content.get("media_ids") or [])
            image_path = str(content.get("image_path") or "").strip()
            if image_path and not media_ids:
                uploaded = await self._upload_media(image_path)
                media_id = str(uploaded.get("media_id") or "")
                if not media_id:
                    return {
                        "platform": "twitter",
                        "status": "error",
                        "error": f"media_upload_failed: {uploaded.get('error', 'unknown')}",
                    }
                media_ids = [media_id]

            if content.get("reply_to"):
                payload["reply"] = {"in_reply_to_tweet_id": content["reply_to"]}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}

            headers = {
                "Authorization": self._oauth1_header("POST", url),
                "Content-Type": "application/json",
            }

            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if resp.status in (200, 201):
                    tweet = data.get("data", {})
                    tweet_id = tweet.get("id", "")
                    if not str(tweet_id or "").strip():
                        # API acknowledged but no tweet id -> cannot satisfy evidence contract.
                        # Try browser fallback if we have a valid storage state.
                        if self._storage_state_path.exists():
                            return await self._publish_via_browser(content or {})
                        return {"platform": "twitter", "status": "error", "error": "tweet_id_missing_in_api_response"}
                    tweet_url = f"https://x.com/i/status/{tweet_id}" if tweet_id else ""
                    logger.info(
                        f"Tweet posted: {tweet_id}",
                        extra={"event": "twitter_publish_ok", "context": {"tweet_id": tweet_id}},
                    )
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"twitter tweet_id={tweet_id}",
                            evidence=tweet_url,
                            source="twitter.publish",
                            evidence_dict={"platform": "twitter", "tweet_id": tweet_id, "url": tweet_url},
                        )
                    except Exception:
                        pass
                    return {
                        "platform": "twitter",
                        "status": "published",
                        "tweet_id": tweet_id,
                        "url": tweet_url,
                        "text": text,
                    }
                else:
                    error = data.get("detail", data.get("title", str(resp.status)))
                    logger.warning(f"Tweet failed: {error}", extra={"event": "twitter_publish_fail"})

                    # Save to file if permissions/billing issue — don't claim published
                    if "permission" in error.lower() or "oauth1" in error.lower() or "credit" in error.lower() or resp.status == 403:
                        return await self._save_draft_tweet(text, error)

                    return {"platform": "twitter", "status": "error", "error": error}

        except Exception as e:
            logger.error(f"Twitter publish error: {e}", exc_info=True)
            return {"platform": "twitter", "status": "error", "error": str(e)}

    async def _publish_via_browser(self, content: dict) -> dict:
        if not self._storage_state_path.exists():
            return {
                "platform": "twitter",
                "status": "needs_browser_login",
                "error": "Twitter browser session required.",
                "storage_state": str(self._storage_state_path),
            }
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {"platform": "twitter", "status": "error", "error": "playwright_not_installed"}

        text = str(content.get("text", "") or "").strip()
        if not text:
            return {"platform": "twitter", "status": "error", "error": "No text provided"}
        if len(text) > 280:
            text = text[:277] + "..."
        image_path = str(content.get("image_path") or "").strip()
        shot = str(PROJECT_ROOT / "runtime" / "twitter_browser_publish.png")

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
                await page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(1500)
                current = (page.url or "").lower()
                if any(x in current for x in ("/login", "/i/flow/login", "/signup")):
                    return {
                        "platform": "twitter",
                        "status": "needs_browser_login",
                        "error": "Stored Twitter/X session expired.",
                        "storage_state": str(self._storage_state_path),
                    }

                textbox = None
                compose_selectors = (
                    "div[data-testid='tweetTextarea_0']",
                    "div[role='textbox'][data-testid='tweetTextarea_0']",
                    "div[aria-label='Post text']",
                    "div[role='textbox']",
                )
                for sel in compose_selectors:
                    loc = page.locator(sel)
                    if await loc.count():
                        textbox = loc.first
                        break
                if textbox is None:
                    try:
                        new_btn = page.locator("[data-testid='SideNav_NewTweet_Button']")
                        if await new_btn.count():
                            await new_btn.first.click(timeout=2500)
                            await page.wait_for_timeout(1200)
                    except Exception:
                        pass
                    for sel in compose_selectors:
                        loc = page.locator(sel)
                        if await loc.count():
                            textbox = loc.first
                            break
                if textbox is None:
                    return {"platform": "twitter", "status": "error", "error": "tweet_textbox_not_found"}
                await textbox.click(timeout=2000)
                await page.keyboard.type(text, delay=6)

                if image_path and os.path.isfile(image_path):
                    try:
                        fi = page.locator("input[type='file']")
                        if await fi.count():
                            await fi.first.set_input_files(image_path)
                            await page.wait_for_timeout(1200)
                    except Exception:
                        pass

                posted = False
                for sel in ("button[data-testid='tweetButtonInline']", "button[data-testid='tweetButton']"):
                    try:
                        btn = page.locator(sel)
                        if await btn.count():
                            await btn.first.click(timeout=2500)
                            posted = True
                            break
                    except Exception:
                        continue
                if not posted:
                    try:
                        btn = page.get_by_role("button", name="Post")
                        if await btn.count():
                            await btn.first.click(timeout=2500)
                            posted = True
                    except Exception:
                        pass

                await page.wait_for_timeout(2500)
                tweet_url = ""
                try:
                    href = await page.locator("a[href*='/status/']").first.get_attribute("href")
                    if href:
                        tweet_url = f"https://x.com{href}" if href.startswith("/") else href
                except Exception:
                    pass
                if not tweet_url:
                    try:
                        cur = str(page.url or "")
                        if "/status/" in cur:
                            tweet_url = cur
                    except Exception:
                        pass
                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass

                status = "published" if (posted and tweet_url) else "prepared"
                try:
                    ExecutionFacts().record(
                        action="platform:publish",
                        status=status,
                        detail=f"twitter browser {status}",
                        evidence=tweet_url or "https://x.com/home",
                        source="twitter.publish.browser",
                        evidence_dict={"platform": "twitter", "status": status, "url": tweet_url},
                    )
                except Exception:
                    pass
                return {
                    "platform": "twitter",
                    "status": status,
                    "url": tweet_url or "https://x.com/home",
                    "mode": "browser_only",
                    "screenshot_path": shot,
                }
        except Exception as e:
            return {"platform": "twitter", "status": "error", "error": str(e), "screenshot_path": shot}
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

    async def _upload_media(self, image_path: str) -> dict:
        if not image_path:
            return {"ok": False, "error": "image_path_required"}
        if not os.path.isfile(image_path):
            return {"ok": False, "error": "image_not_found"}
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"ok": False, "error": "not_authenticated"}
        try:
            session = await self._get_session()
            headers = {"Authorization": self._oauth1_header("POST", UPLOAD_API_V1)}
            form = aiohttp.FormData()
            with open(image_path, "rb") as fh:
                form.add_field("media", fh, filename=os.path.basename(image_path), content_type="application/octet-stream")
                async with session.post(
                    UPLOAD_API_V1,
                    headers=headers,
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status in (200, 201):
                        media_id = str(data.get("media_id_string") or data.get("media_id") or "")
                        if media_id:
                            return {"ok": True, "media_id": media_id}
                    return {"ok": False, "error": str(data)[:300]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def delete_tweet(self, tweet_id: str) -> dict:
        """DELETE /2/tweets/{id} — cleanup helper for live probes/tests."""
        if not tweet_id:
            return {"platform": "twitter", "status": "error", "error": "tweet_id required"}
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "twitter", "status": "not_authenticated"}
        try:
            session = await self._get_session()
            url = f"{API_V2}/tweets/{tweet_id}"
            headers = {"Authorization": self._oauth1_header("DELETE", url)}
            async with session.delete(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if resp.status in (200, 202):
                    try:
                        ExecutionFacts().record(
                            action="platform:cleanup",
                            status="success",
                            detail=f"twitter delete tweet_id={tweet_id}",
                            evidence=f"https://x.com/i/status/{tweet_id}",
                            source="twitter.delete",
                            evidence_dict={"platform": "twitter", "tweet_id": tweet_id},
                        )
                    except Exception:
                        pass
                    return {"platform": "twitter", "status": "deleted", "tweet_id": tweet_id, "data": data}
                return {"platform": "twitter", "status": "error", "error": str(data)[:300]}
        except Exception as e:
            return {"platform": "twitter", "status": "error", "error": str(e)}

    async def _save_draft_tweet(self, text: str, error: str) -> dict:
        """Save tweet to file when write permissions are not available."""
        from pathlib import Path
        import time as _time

        out = PROJECT_ROOT / "output" / "tweets"
        out.mkdir(parents=True, exist_ok=True)
        fp = out / f"tweet_{int(_time.time())}.txt"
        fp.write_text(text, encoding="utf-8")
        logger.info(
            f"Tweet saved to file (no write perms): {fp}",
            extra={"event": "twitter_draft_saved", "context": {"path": str(fp)}},
        )
        try:
            ExecutionFacts().record(
                action="platform:publish",
                status="prepared",
                detail="twitter draft saved",
                evidence=str(fp),
                source="twitter.publish",
                evidence_dict={"platform": "twitter", "draft_path": str(fp)},
            )
        except Exception:
            pass
        return {
            "platform": "twitter",
            "status": "draft_saved",
            "file_path": str(fp),
            "text": text,
            "note": f"Готово к публикации, жду разрешения. Ошибка: {error}",
        }

    async def get_analytics(self) -> dict:
        """Get basic account metrics."""
        if not self._authenticated:
            await self.authenticate()
        if not self._user_id:
            return {"platform": "twitter", "followers": 0, "tweets": 0}

        try:
            session = await self._get_session()
            url = f"{API_V2}/users/{self._user_id}?user.fields=public_metrics"
            headers = {"Authorization": f"Bearer {self._bearer_token}"}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    metrics = data.get("data", {}).get("public_metrics", {})
                    return {
                        "platform": "twitter",
                        "followers": metrics.get("followers_count", 0),
                        "following": metrics.get("following_count", 0),
                        "tweets": metrics.get("tweet_count", 0),
                        "listed": metrics.get("listed_count", 0),
                    }
        except Exception as e:
            logger.error(f"Twitter analytics error: {e}", exc_info=True)
        return {"platform": "twitter", "followers": 0, "tweets": 0}

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
