"""RedditPlatform — lightweight Reddit publish adapter (SDK-pack step)."""

from __future__ import annotations

import asyncio
import aiohttp
import hashlib
import os
import re
import time
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

    async def _upload_image_to_cloudinary(self, image_path: str) -> str:
        """Upload local image and return public URL, or empty string on failure."""
        p = Path(str(image_path or "").strip())
        if not p.exists() or not p.is_file():
            return ""
        cloud = str(getattr(settings, "CLOUDINARY_CLOUD_NAME", "") or "").strip()
        api_key = str(getattr(settings, "CLOUDINARY_API_KEY", "") or "").strip()
        api_secret = str(getattr(settings, "CLOUDINARY_API_SECRET", "") or "").strip()
        if not cloud or not api_key or not api_secret:
            return ""
        ts = int(time.time())
        sig_src = f"folder=vito_reddit&timestamp={ts}{api_secret}"
        signature = hashlib.sha1(sig_src.encode("utf-8")).hexdigest()
        url = f"https://api.cloudinary.com/v1_1/{cloud}/image/upload"
        try:
            sess = await self._get_session()
            data = aiohttp.FormData()
            data.add_field("file", p.read_bytes(), filename=p.name, content_type="image/png")
            data.add_field("folder", "vito_reddit")
            data.add_field("timestamp", str(ts))
            data.add_field("api_key", api_key)
            data.add_field("signature", signature)
            async with sess.post(url, data=data, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                body = await resp.json(content_type=None)
                if resp.status in (200, 201):
                    return str(body.get("secure_url") or body.get("url") or "").strip()
        except Exception:
            return ""
        return ""

    async def _publish_via_api(self, subreddit: str, title: str, body: str, link_url: str) -> dict:
        """API submit fallback to avoid fragile browser composer/captcha loops."""
        if not self._authenticated:
            ok = await self.authenticate()
            if not ok:
                return {"platform": "reddit", "status": "not_authenticated"}
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
                payload = await resp.json(content_type=None)
                errs = (((payload or {}).get("json") or {}).get("errors") or [])
                if resp.status in (200, 201) and not errs:
                    jd = ((payload or {}).get("json") or {}).get("data") or {}
                    post_url = str(jd.get("url") or "").strip()
                    if post_url and post_url.startswith("/"):
                        post_url = f"https://www.reddit.com{post_url}"
                    if not post_url:
                        post_url = f"https://reddit.com/r/{subreddit}/new"
                    return {"platform": "reddit", "status": "published", "url": post_url}
                return {"platform": "reddit", "status": "error", "error": str(errs)[:300]}
        except Exception as e:
            return {"platform": "reddit", "status": "error", "error": str(e)}

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
            res = await self._publish_via_browser(content or {})
            # Retry browser flow for transient Reddit anti-bot/captcha states.
            if str(res.get("status") or "").strip().lower() in {"prepared", "blocked"}:
                for attempt in range(2):
                    await asyncio.sleep(2.0 + attempt * 2.0)
                    probe = await self._publish_via_browser(content or {})
                    if str(probe.get("status") or "").strip().lower() == "published":
                        return probe
                    # keep the latest result details for reporting/fallbacks
                    res = probe
            if str(res.get("status") or "").strip().lower() in {"prepared", "blocked"}:
                # If IMAGE submit path hits captcha/challenge, retry as LINK post with uploaded image URL.
                image_path = str((content or {}).get("image_path", "")).strip()
                err = str(res.get("error") or "").lower()
                if image_path and ("captcha" in err or "submit_rejected" in err):
                    img_url = await self._upload_image_to_cloudinary(image_path)
                    if img_url:
                        retry_payload = dict(content or {})
                        retry_payload["url"] = img_url
                        retry_payload["image_url"] = img_url
                        retry_payload["image_path"] = ""
                        retry_res = await self._publish_via_browser(retry_payload)
                        if str(retry_res.get("status") or "").strip().lower() in {"prepared", "blocked"}:
                            await asyncio.sleep(2.0)
                            retry_res2 = await self._publish_via_browser(retry_payload)
                            if str(retry_res2.get("status") or "").strip().lower() == "published":
                                return retry_res2
                            retry_res = retry_res2
                        if str(retry_res.get("status") or "").strip().lower() == "published":
                            return retry_res
                # Last fallback: API submit to avoid browser captcha/overlay issues.
                subreddit = str(content.get("subreddit", "")).strip() or "test"
                title = str(content.get("title", "")).strip()
                body = str(content.get("text", "")).strip()
                link_url = str(content.get("url", "") or content.get("image_url", "")).strip()
                image_path = str(content.get("image_path", "")).strip()
                if image_path and not link_url:
                    link_url = await self._upload_image_to_cloudinary(image_path)
                if title:
                    api_res = await self._publish_via_api(subreddit, title, body, link_url)
                    if str(api_res.get("status") or "").strip().lower() == "published":
                        return api_res
            return res

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
        if image_path and not link_url:
            link_url = await self._upload_image_to_cloudinary(image_path)
        if not subreddit or not title:
            return {"platform": "reddit", "status": "error", "error": "subreddit/title required"}
        if image_path and not link_url:
            return {
                "platform": "reddit",
                "status": "error",
                "error": "image_path_not_supported_without_url; provide image_url/url for link post",
            }

        res = await self._publish_via_api(subreddit, title, body, link_url)
        if str(res.get("status") or "").lower() == "published":
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="published",
                    detail=f"reddit subreddit={subreddit} title={title[:80]}",
                    evidence=str(res.get("url") or ""),
                    source="reddit.publish",
                    evidence_dict={"platform": "reddit", "subreddit": subreddit, "title": title},
                )
            except Exception:
                pass
        return res

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
        profile_name = ""
        post_to_profile = False
        if subreddit.lower().startswith("u_"):
            profile_name = subreddit[2:].strip()
            post_to_profile = bool(profile_name)
        elif subreddit.lower().startswith("user/"):
            profile_name = subreddit.split("/", 1)[1].strip()
            post_to_profile = bool(profile_name)
        title = str(content.get("title", "")).strip()
        body = str(content.get("text", "")).strip()
        link_url = str(content.get("url", "") or content.get("image_url", "")).strip()
        image_path = str(content.get("image_path", "")).strip()
        prefer_image_post = bool(image_path and Path(image_path).is_file() and not link_url)
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
                submit_type = "IMAGE" if prefer_image_post else "TEXT"
                await page.goto(
                    f"https://www.reddit.com/r/{subreddit}/submit/?type={submit_type}",
                    wait_until="domcontentloaded",
                    timeout=90000,
                )
                await page.wait_for_timeout(1200)
                current = (page.url or "").lower()
                body_text = (await page.text_content("body") or "").lower()
                post_url = str(page.url or "")
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
                if prefer_image_post:
                    uploaded = False
                    for sel in (
                        "input[type='file']",
                        "input[accept*='image']",
                    ):
                        try:
                            fi = page.locator(sel)
                            if await fi.count():
                                await fi.first.set_input_files(image_path)
                                await page.wait_for_timeout(2200)
                                uploaded = True
                                break
                        except Exception:
                            continue
                    if not uploaded:
                        return {
                            "platform": "reddit",
                            "status": "blocked",
                            "error": "image_upload_control_not_found",
                            "url": page.url,
                        }
                elif link_url:
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
                # Fallback verify: check owner's "submitted" page for recently created title.
                if "/comments/" not in post_url:
                    try:
                        profile_user = str(getattr(settings, "REDDIT_USERNAME", "") or "").strip()
                        if profile_user:
                            await page.goto(
                                f"https://www.reddit.com/user/{profile_user}/submitted/",
                                wait_until="domcontentloaded",
                                timeout=90000,
                            )
                            await page.wait_for_timeout(2200)
                            matched = await page.evaluate(
                                """(needle) => {
                                    const key = String(needle || '').trim().toLowerCase();
                                    if (!key) return "";
                                    const links = Array.from(document.querySelectorAll("a[href*='/comments/']"));
                                    for (const a of links) {
                                        const href = a.getAttribute('href') || '';
                                        if (!href.includes('/comments/')) continue;
                                        const card = a.closest('article,shreddit-post,div');
                                        const txt = ((card && card.textContent) || a.textContent || '').toLowerCase();
                                        if (txt.includes(key)) {
                                            return href.startsWith('http') ? href : `https://www.reddit.com${href}`;
                                        }
                                    }
                                    return "";
                                }""",
                                title[:120],
                            )
                            if matched:
                                post_url = str(matched)
                    except Exception:
                        pass
                # Legacy fallback: old.reddit submit form is often less fragile than new UI.
                if "/comments/" not in post_url:
                    try:
                        old_submit_url = "https://old.reddit.com/submit"
                        if post_to_profile and profile_name:
                            old_submit_url = f"https://old.reddit.com/user/{profile_name}/submit"
                        await page.goto(old_submit_url, wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(1500)
                        # Accept cookie banner if present (can block submit controls).
                        for sel in (
                            "#gdpr-banner button",
                            "button:has-text('CONTINUE')",
                            "button:has-text('Continue')",
                            "button:has-text('Продолжить')",
                        ):
                            try:
                                b = page.locator(sel)
                                if await b.count():
                                    await b.first.click(timeout=1200)
                                    await page.wait_for_timeout(400)
                                    break
                            except Exception:
                                continue
                        # choose post type based on payload: image/link when image/url is present, otherwise self text post.
                        if prefer_image_post or link_url:
                            try:
                                await page.check("input#kind-link", timeout=1500)
                            except Exception:
                                pass
                            try:
                                await page.check("input[name='kind'][value='link']", timeout=1500)
                            except Exception:
                                pass
                            for sel in ("#link-button", "a:has-text('link')", "button:has-text('link')"):
                                try:
                                    loc = page.locator(sel)
                                    if await loc.count():
                                        await loc.first.click(timeout=1500)
                                        await page.wait_for_timeout(500)
                                        break
                                except Exception:
                                    continue
                        else:
                            try:
                                await page.check("input#kind-self", timeout=1500)
                            except Exception:
                                pass
                            try:
                                await page.check("input[name='kind'][value='self']", timeout=1500)
                            except Exception:
                                pass
                            for sel in ("#text-button", "a:has-text('text')", "button:has-text('text')"):
                                try:
                                    loc = page.locator(sel)
                                    if await loc.count():
                                        await loc.first.click(timeout=1500)
                                        await page.wait_for_timeout(500)
                                        break
                                except Exception:
                                    continue
                        if post_to_profile:
                            # old.reddit profile submit is less reliable via standard check(); set it directly.
                            try:
                                await page.evaluate(
                                    """() => {
                                        const profile = document.querySelector('#submit_type_profile');
                                        const sub = document.querySelector('#submit_type_subreddit');
                                        if (sub) sub.checked = false;
                                        if (profile) {
                                            profile.checked = true;
                                            profile.dispatchEvent(new Event('change', { bubbles: true }));
                                            profile.dispatchEvent(new Event('click', { bubbles: true }));
                                        }
                                        const sr = document.querySelector('#sr-autocomplete');
                                        if (sr) sr.value = '';
                                        const selected = document.querySelector('#selected_sr_names');
                                        if (selected) selected.value = '';
                                    }"""
                                )
                                await page.wait_for_timeout(300)
                            except Exception:
                                pass
                        else:
                            try:
                                await page.fill("input[name='sr']", subreddit, timeout=2000)
                            except Exception:
                                pass
                        await page.fill("textarea[name='title']", title[:300], timeout=2500)
                        if prefer_image_post:
                            try:
                                img = page.locator("#image")
                                if await img.count():
                                    await img.first.set_input_files(image_path)
                                    await page.wait_for_timeout(1200)
                                    for _ in range(45):
                                        body_now = ((await page.text_content("body")) or "").lower()
                                        if "your video has uploaded" in body_now or "choose a thumbnail" in body_now:
                                            break
                                        await page.wait_for_timeout(1000)
                            except Exception:
                                pass
                        elif link_url:
                            try:
                                await page.fill("input[name='url']", link_url, timeout=2500)
                            except Exception:
                                pass
                        elif body:
                            try:
                                await page.fill("textarea[name='text']", body[:40000], timeout=2500)
                            except Exception:
                                pass
                        # If text field becomes enabled after media upload, populate it.
                        if body:
                            try:
                                txt = page.locator("textarea[name='text']")
                                if await txt.count():
                                    disabled = await txt.first.get_attribute("disabled")
                                    if disabled is None:
                                        await txt.first.fill(body[:40000], timeout=2500)
                            except Exception:
                                pass
                        # Solve old.reddit reCAPTCHA if present.
                        try:
                            has_captcha = await page.evaluate(
                                """() => !!(
                                    document.querySelector('[data-sitekey]') ||
                                    document.querySelector('iframe[src*=\"recaptcha\"]') ||
                                    document.querySelector('.g-recaptcha')
                                )"""
                            )
                        except Exception:
                            has_captcha = False
                        if has_captcha:
                            try:
                                from modules.captcha_solver import CaptchaSolver
                                token = await CaptchaSolver.get_instance().solve_playwright_recaptcha(page)
                                if not token:
                                    return {
                                        "platform": "reddit",
                                        "status": "blocked",
                                        "error": "captcha_required",
                                        "url": page.url,
                                        "screenshot_path": shot,
                                    }
                            except Exception:
                                return {
                                    "platform": "reddit",
                                    "status": "blocked",
                                    "error": "captcha_required",
                                    "url": page.url,
                                    "screenshot_path": shot,
                                }
                        for sel in (
                            "button.btn[name='submit'][value='form']",
                            "button[name='submit'][value='form']",
                            "button[type='submit']",
                            "button:has-text('submit')",
                            "input[type='submit']",
                        ):
                            btn = page.locator(sel)
                            if await btn.count():
                                try:
                                    await btn.first.click(timeout=2500)
                                    posted = True
                                    break
                                except Exception:
                                    continue
                        await page.wait_for_timeout(2600)
                        current2 = str(page.url or "")
                        if "/comments/" in current2:
                            post_url = current2
                        else:
                            # old.reddit may keep the user on /submit even after a successful token
                            # injection; force form submission once before treating it as blocked.
                            try:
                                forced = await page.evaluate(
                                    """() => {
                                        const form = document.querySelector('#newlink');
                                        if (!form) return false;
                                        try { form.requestSubmit ? form.requestSubmit() : form.submit(); return true; }
                                        catch (_) { return false; }
                                    }"""
                                )
                                if forced:
                                    await page.wait_for_timeout(3000)
                                    current2 = str(page.url or "")
                                    if "/comments/" in current2:
                                        post_url = current2
                            except Exception:
                                pass
                        reject_text = ""
                        try:
                            reject_text = (await page.text_content("body") or "").lower()
                        except Exception:
                            reject_text = ""
                        if "that was a tricky one" in reject_text and "/comments/" not in post_url:
                            return {
                                "platform": "reddit",
                                "status": "blocked",
                                "error": "submit_rejected_after_media_upload",
                                "url": page.url,
                                "screenshot_path": shot,
                            }
                        if has_captcha and "/comments/" not in post_url:
                            return {
                                "platform": "reddit",
                                "status": "blocked",
                                "error": "captcha_not_solved_or_submit_rejected",
                                "url": page.url,
                                "screenshot_path": shot,
                            }
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
