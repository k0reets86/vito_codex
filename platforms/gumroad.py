"""GumroadPlatform — интеграция с Gumroad API v2 + Playwright browser automation.

API: GET products, enable/disable/delete. POST/PUT products = 404 (removed by Gumroad).
Product creation: ONLY via Playwright + session cookie (browser automation).
See memory/gumroad_publishing.md for full experience log.
"""

import asyncio
import os
import json
from pathlib import Path
from typing import Any

import aiohttp

from config.paths import PROJECT_ROOT
from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform
from platforms.gumroad_selector_bank import (
    CONTENT_TAB_SELECTORS,
    NEXT_SELECTORS,
    PRODUCT_TAB_SELECTORS,
    PUBLISH_SELECTORS,
    SAVE_SELECTORS,
    SHARE_TAB_SELECTORS,
)
from modules.network_utils import network_available, network_status
from modules.execution_facts import ExecutionFacts
from modules.listing_optimizer import optimize_listing_payload

logger = get_logger("gumroad", agent="gumroad")
API_BASE = "https://api.gumroad.com/v2"
COOKIE_FILE = Path("/tmp/gumroad_cookie.txt")
LOGIN_SHOT = Path("/tmp/gumroad_login.png")
PUBLISH_SHOT = Path("/tmp/gumroad_publish.png")
STORAGE_STATE_FILE = PROJECT_ROOT / "runtime" / "gumroad_storage_state.json"


async def _launch_browser(p):
    try:
        chromium_exe = None
        base = Path.home() / ".cache" / "ms-playwright"
        # Prefer headless_shell for lower resource usage
        for cand in sorted(base.glob("chromium_headless_shell-*/chrome-linux/headless_shell"), reverse=True):
            chromium_exe = cand
            break
        if not chromium_exe:
            for cand in sorted(base.glob("chromium-*/chrome-linux/chrome"), reverse=True):
                chromium_exe = cand
                break
        headless = os.environ.get("VITO_BROWSER_HEADLESS", "1").lower() not in ("0", "false", "no")
        constrained = bool(getattr(settings, "BROWSER_CONSTRAINED_MODE", True))
        launch_kwargs = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-crashpad",
                "--no-crash-upload",
                "--disable-features=Crashpad",
                "--disable-site-isolation-trials",
                "--renderer-process-limit=1",
            ],
            "chromium_sandbox": False,
        }
        if constrained:
            launch_kwargs["args"].extend(["--no-zygote", "--single-process"])
        if chromium_exe and chromium_exe.exists():
            launch_kwargs["executable_path"] = str(chromium_exe)
        return await p.chromium.launch(**launch_kwargs)
    except Exception as e:
        logger.warning(f"Chromium launch failed, falling back to Firefox: {e}")
        try:
            return await p.firefox.launch(headless=True)
        except Exception as e2:
            logger.error(f"Firefox launch failed: {e2}")
            raise


async def _launch_gumroad_publish_browser(p):
    """Stable browser profile for Gumroad creation flow."""
    headless = os.environ.get("VITO_BROWSER_HEADLESS", "1").lower() not in ("0", "false", "no")
    return await p.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-blink-features=AutomationControlled",
        ],
        chromium_sandbox=False,
    )


class GumroadPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="gumroad", **kwargs)
        self._mode = str(getattr(settings, "GUMROAD_MODE", "api") or "api").strip().lower()
        # Пробуем access_token, fallback на app_secret
        self._access_token = (
            getattr(settings, "GUMROAD_API_KEY", "")
            or getattr(settings, "GUMROAD_APP_SECRET", "")
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _params(self, extra: dict | None = None) -> dict:
        """Базовые параметры с access_token."""
        params = {"access_token": self._access_token}
        if extra:
            params.update(extra)
        return params

    async def authenticate(self) -> bool:
        """GET /v2/user — проверка авторизации."""
        if self._mode in {"browser", "browser_only"}:
            if COOKIE_FILE.exists() and COOKIE_FILE.read_text(encoding="utf-8", errors="ignore").strip():
                self._authenticated = True
                return True
            storage = Path(str(getattr(settings, "GUMROAD_STORAGE_STATE_FILE", "runtime/gumroad_storage_state.json") or "runtime/gumroad_storage_state.json"))
            if not storage.is_absolute():
                storage = PROJECT_ROOT / storage
            if storage.exists():
                try:
                    import json as _json
                    data = _json.loads(storage.read_text(encoding="utf-8"))
                    cookies = data.get("cookies") if isinstance(data, dict) else None
                    self._authenticated = isinstance(cookies, list) and len(cookies) > 0
                    return self._authenticated
                except Exception:
                    self._authenticated = False
                    return False
            self._authenticated = False
            return False
        if not self._access_token:
            self._authenticated = False
            return False
        net = network_status(["api.gumroad.com", "gumroad.com"])
        if not net["ok"]:
            logger.warning(
                f"Network unavailable for Gumroad API: {net['reason']}",
                extra={"event": "gumroad_network_down", "context": net},
            )
            self._authenticated = False
            return False
        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/user",
                params=self._params(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                self._authenticated = resp.status == 200
                if self._authenticated:
                    data = await resp.json()
                    user = data.get("user", {})
                    logger.info(
                        f"Gumroad авторизация: {user.get('name', 'unknown')}",
                        extra={"event": "gumroad_auth_ok", "context": {"user": user.get("name")}},
                    )
                else:
                    body = await resp.text()
                    logger.warning(
                        f"Gumroad авторизация не удалась: {resp.status} {body[:200]}",
                        extra={"event": "gumroad_auth_fail", "context": {"status": resp.status}},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Gumroad auth error: {e}", extra={"event": "gumroad_auth_error"}, exc_info=True)
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Create and publish a product on Gumroad via Playwright browser automation.

        content: {
            name: str,               # Product title
            price: int,              # Price in dollars (not cents)
            description: str,        # Product description text
            summary: str,            # Short summary (1-2 sentences)
            pdf_path: str,           # Path to PDF file
            cover_path: str,         # Path to cover image (1280x720)
            thumb_path: str,         # Path to thumbnail (600x600)
        }

        Gumroad API does NOT support product creation (404). Uses Playwright + session cookie.
        """
        content = optimize_listing_payload("gumroad", content or {})
        # Dry-run path: validate payload and return deterministic evidence without touching live account.
        if bool(content.get("dry_run")):
            name = str(content.get("name") or "VITO Gumroad DryRun").strip()
            price = content.get("price", 0)
            pdf_path = str(content.get("pdf_path") or "")
            cover_path = str(content.get("cover_path") or "")
            thumb_path = str(content.get("thumb_path") or "")
            missing = []
            for pth in (pdf_path, cover_path, thumb_path):
                if pth and not Path(pth).exists():
                    missing.append(pth)
            if missing:
                result = {
                    "platform": "gumroad",
                    "status": "error",
                    "error": f"missing_file:{missing[0]}",
                }
            else:
                result = {
                    "platform": "gumroad",
                    "status": "prepared",
                    "url": f"dryrun://gumroad/{name[:60].replace(' ', '_')}",
                    "evidence": {
                        "name": name,
                        "price": price,
                        "pdf_path": pdf_path,
                        "cover_path": cover_path,
                        "thumb_path": thumb_path,
                    },
                }
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status=result.get("status", "unknown"),
                    detail=f"gumroad dry_run name={name[:80]}",
                    evidence=str(result.get("url", "")),
                    source="gumroad.publish",
                    evidence_dict={"platform": "gumroad", "dry_run": True, "result": result},
                )
            except Exception:
                pass
            return result

        # Safety policy: editing existing live products must be explicitly confirmed,
        # unless autonomy mode explicitly allows controlled updates.
        operation = str(content.get("operation") or "create").strip().lower()
        autonomy_allow_existing = bool(getattr(settings, "AUTONOMY_ALLOW_EXISTING_PRODUCT_UPDATE", False))
        if bool(getattr(settings, "PUBLISH_CREATE_GUARD_ENABLED", True)):
            if operation in {"create", "new"} and bool(content.get("allow_existing_update")):
                return {
                    "platform": "gumroad",
                    "status": "blocked",
                    "error": "create_mode_forbids_existing_update",
                }
        if content.get("allow_existing_update") and not (content.get("owner_edit_confirmed") or autonomy_allow_existing):
            return {
                "platform": "gumroad",
                "status": "blocked",
                "error": "existing_update_requires_owner_confirmation",
            }
        if content.get("allow_existing_update"):
            target_product_id = str(content.get("target_product_id") or "").strip()
            target_slug = str(content.get("target_slug") or "").strip()
            if not (target_product_id or target_slug):
                return {
                    "platform": "gumroad",
                    "status": "blocked",
                    "error": "existing_update_requires_target_product_id_or_slug",
                }

        # Validate required assets
        pdf_path = content.get("pdf_path", "")
        cover_path = content.get("cover_path", "")
        thumb_path = content.get("thumb_path", "")
        product_id = ""
        for path in (pdf_path, cover_path, thumb_path):
            if path and not Path(path).exists():
                return {"platform": "gumroad", "status": "error", "error": f"missing_file:{path}"}
        if pdf_path and Path(pdf_path).stat().st_size > 16 * 1024 * 1024:
            return {"platform": "gumroad", "status": "error", "error": "pdf_too_large_gt_16mb"}

        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                # Gumroad API might be unavailable; proceed with browser flow
                logger.warning("Gumroad API auth failed; proceeding with browser publish", extra={"event": "gumroad_auth_skip"})

        # Try browser-based creation (ensure session cookie)
        net = network_status(["gumroad.com"])
        if not net["ok"]:
            return {
                "platform": "gumroad",
                "status": "network_unavailable",
                "error": f"Network unavailable: {net['reason']}",
            }
        if not COOKIE_FILE.exists() or not COOKIE_FILE.read_text().strip():
            await self._ensure_session_cookie()
        draft_only = bool(content.get("draft_only"))
        keep_unpublished = bool(content.get("keep_unpublished")) or draft_only
        allow_existing_update = bool(content.get("allow_existing_update")) and bool(content.get("owner_edit_confirmed"))
        target_product_id = str(content.get("target_product_id") or "").strip()

        async def _fallback_existing_publish(reason: str) -> dict | None:
            """Fallback: for explicit existing-product flow, at least enforce publish/draft state via API."""
            if not (allow_existing_update and target_product_id):
                return None
            try:
                if keep_unpublished:
                    out = await self.disable_product(target_product_id)
                    if str(out.get("status") or "") in {"draft", "disabled"}:
                        out["fallback"] = "api_toggle_after_browser_failure"
                        out["fallback_reason"] = reason
                        return out
                else:
                    out = await self.enable_product(target_product_id)
                    if str(out.get("status") or "") == "published":
                        out["fallback"] = "api_toggle_after_browser_failure"
                        out["fallback_reason"] = reason
                        return out
            except Exception:
                return None
            return None
        try:
            result = await asyncio.wait_for(self._publish_via_browser(content), timeout=180)
            # Record execution facts to prevent false success claims
            try:
                facts = ExecutionFacts()
                evidence = result.get("url") or result.get("screenshot_path", "")
                sig = str(content.get("signature", "")).strip()
                detail = f"gumroad sig={sig}" if sig else "gumroad"
                facts.record(
                    action="platform:publish",
                    status=result.get("status", "unknown"),
                    detail=detail,
                    evidence=evidence,
                    source="gumroad.publish",
                    evidence_dict={
                        "platform": "gumroad",
                        "status": result.get("status"),
                        "url": result.get("url", ""),
                        "screenshot_path": result.get("screenshot_path", ""),
                        "product_id": result.get("product_id", ""),
                    },
                )
            except Exception:
                pass
            if str(result.get("status") or "") in {"timeout", "error", "cookie_expired", "daily_limit"}:
                fb = await _fallback_existing_publish(str(result.get("error") or result.get("status") or "browser_publish_failed"))
                if fb is not None:
                    return fb
            return result
        except asyncio.TimeoutError:
            logger.error("Gumroad publish timed out")
            fb = await _fallback_existing_publish("browser_publish_timeout")
            if fb is not None:
                return fb
            return {"platform": "gumroad", "status": "timeout", "error": "Publish timed out"}

    async def _ensure_session_cookie(self) -> bool:
        """Login via Playwright using email/password to obtain session cookie."""
        email = getattr(settings, "GUMROAD_EMAIL", "")
        password = getattr(settings, "GUMROAD_PASSWORD", "")
        if not email or not password:
            logger.warning("Gumroad login missing email/password")
            return False
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed")
            return False
        try:
            async with async_playwright() as p:
                br = await _launch_gumroad_publish_browser(p)
                ctx = await br.new_context(
                    viewport={"width": 1280, "height": 1400},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                )
                page = await ctx.new_page()
                page.set_default_timeout(20000)
                await page.goto("https://gumroad.com/login", wait_until="networkidle")
                await page.fill('input[type="email"]', email)
                await page.fill('input[type="password"]', password)
                await page.click('button[type="submit"]')
                await asyncio.sleep(4)
                # If OTP/2FA appears, try code from /tmp/gumroad_2fa.txt
                if "two-factor" in page.url or await page.locator('input[name*="otp"]').count() > 0:
                    code_path = Path("/tmp/gumroad_2fa.txt")
                    if code_path.exists():
                        code = code_path.read_text().strip()
                        try:
                            otp = page.locator('input[name*="otp"]').first
                            await otp.fill(code)
                            await page.click('button[type="submit"]')
                            await asyncio.sleep(3)
                        except Exception:
                            pass
                    await page.screenshot(path=str(LOGIN_SHOT), full_page=True)
                    if "login" in page.url:
                        await br.close()
                        logger.warning("Gumroad login requires 2FA/OTP")
                        return False
                cookies = await ctx.cookies()
                session_cookie = next((c for c in cookies if c.get("name") == "_gumroad_app_session"), None)
                if session_cookie:
                    COOKIE_FILE.write_text(session_cookie.get("value", "").strip())
                    await page.screenshot(path=str(LOGIN_SHOT), full_page=True)
                    await br.close()
                    logger.info("Gumroad session cookie saved", extra={"event": "gumroad_cookie_saved"})
                    return True
                await page.screenshot(path=str(LOGIN_SHOT), full_page=True)
                await br.close()
                return False
        except Exception as e:
            logger.error(f"Gumroad login error: {e}", exc_info=True)
            return False

    async def _publish_via_browser(self, content: dict) -> dict:
        """Create product via Playwright using session cookie from owner's browser.

        Cookie file: /tmp/gumroad_cookie.txt (_gumroad_app_session value)
        """
        logger.info("Gumroad browser publish start", extra={"event": "gumroad_publish_start"})
        cookie = ""
        if COOKIE_FILE.exists():
            cookie = COOKIE_FILE.read_text().strip()
        if not cookie:
            logger.warning("No Gumroad session cookie. Owner must provide _gumroad_app_session.")
            return {
                "platform": "gumroad",
                "status": "need_cookie",
                "error": "No session cookie. Ask owner for _gumroad_app_session from browser.",
            }

        allow_existing_update = bool(content.get("allow_existing_update")) and bool(content.get("owner_edit_confirmed"))
        target_product_id = str(content.get("target_product_id") or "").strip()
        target_slug = str(content.get("target_slug") or "").strip()
        if allow_existing_update and not (target_product_id or target_slug):
            return {
                "platform": "gumroad",
                "status": "blocked",
                "error": "existing_update_requires_target_product_id_or_slug",
            }

        name = content.get("name", "VITO Product")
        price = str(content.get("price", 9))
        description = content.get("description", "")
        summary = content.get("summary", "")
        pdf_path = content.get("pdf_path", "")
        cover_path = content.get("cover_path", "")
        thumb_path = content.get("thumb_path", "")
        taxonomy_id_cfg = str(content.get("taxonomy_id", "66") or "66")
        tags_cfg = content.get("tags", ["automation", "ai", "productivity", "workflow"]) or ["automation", "ai", "productivity", "workflow"]
        if not isinstance(tags_cfg, list):
            tags_cfg = [str(tags_cfg)]
        tags_cfg = [str(t).strip().lower()[:32] for t in tags_cfg if str(t).strip()][:5]
        if not tags_cfg:
            tags_cfg = ["automation", "ai", "productivity", "workflow"]
        keep_unpublished = bool(content.get("keep_unpublished")) or bool(content.get("draft_only"))
        auth_retry = int(content.get("_auth_retry", 0) or 0)
        gallery_paths_cfg = content.get("gallery_paths", []) or []
        if not isinstance(gallery_paths_cfg, list):
            gallery_paths_cfg = [str(gallery_paths_cfg)]
        gallery_paths = [str(p) for p in gallery_paths_cfg if str(p).strip() and Path(str(p)).exists()]
        before_ids: set[str] = set()
        if not allow_existing_update:
            try:
                existing_before = await self.get_products()
                before_ids = {str((x or {}).get("id") or "") for x in existing_before if (x or {}).get("id")}
            except Exception:
                before_ids = set()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed")
            return {"platform": "gumroad", "status": "error", "error": "playwright not installed"}

        try:
            async with async_playwright() as p:
                br = await _launch_browser(p)
                has_storage = False
                if STORAGE_STATE_FILE.exists():
                    try:
                        parsed = json.loads(STORAGE_STATE_FILE.read_text(encoding="utf-8"))
                        cookies = parsed.get("cookies") if isinstance(parsed, dict) else None
                        has_storage = bool(isinstance(cookies, list) and cookies)
                    except Exception:
                        has_storage = False
                if has_storage:
                    ctx = await br.new_context(
                        storage_state=str(STORAGE_STATE_FILE),
                        viewport={"width": 1280, "height": 1400},
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    )
                else:
                    ctx = await br.new_context(
                        viewport={"width": 1280, "height": 1400},
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    )
                if cookie:
                    await ctx.add_cookies([{
                        "name": "_gumroad_app_session", "value": cookie,
                        "domain": ".gumroad.com", "path": "/", "httpOnly": True,
                        "secure": True, "sameSite": "Lax",
                    }])
                page = await ctx.new_page()
                page.set_default_timeout(20000)
                if keep_unpublished:
                    try:
                        btn_unpub = page.get_by_role("button", name="Unpublish")
                        if await btn_unpub.count() > 0 and await btn_unpub.first.is_visible(timeout=1500):
                            await btn_unpub.first.click(timeout=2500)
                            await asyncio.sleep(1200)
                    except Exception:
                        pass

                # Prefer editing an explicitly targeted existing product only when explicitly allowed.
                slug_from_api = ""
                target_edit_url = ""
                if allow_existing_update:
                    try:
                        existing = await self.get_products()
                        for prod in existing:
                            pid = str(prod.get("id") or "")
                            short = prod.get("short_url", "") or prod.get("url", "")
                            slug_candidate = ""
                            if "/l/" in short:
                                slug_candidate = short.split("/l/")[-1].split("?")[0]
                            elif "gum.co/" in short:
                                slug_candidate = short.rsplit("/", 1)[-1]
                            if (target_product_id and pid == target_product_id) or (target_slug and slug_candidate == target_slug):
                                short = prod.get("short_url", "") or prod.get("url", "")
                                if "/l/" in short:
                                    slug_from_api = short.split("/l/")[-1].split("?")[0]
                                    target_edit_url = short.rstrip("/") + "/edit"
                                elif "gum.co/" in short:
                                    slug_from_api = short.rsplit("/", 1)[-1]
                                    target_edit_url = f"https://gumroad.com/l/{slug_from_api}/edit"
                                break
                    except Exception:
                        slug_from_api = ""
                        target_edit_url = ""

                async def _open_existing_product(preferred_name: str = "", allow_update: bool = False) -> str:
                    if not allow_update:
                        return ""
                    try:
                        existing = await self.get_products()
                        if not existing:
                            return ""
                        # Only explicit target can be opened.
                        slug_local = ""
                        for prod in existing:
                            pid = str(prod.get("id") or "")
                            short = prod.get("short_url", "") or prod.get("url", "")
                            slug_candidate = ""
                            if "/l/" in short:
                                slug_candidate = short.split("/l/")[-1].split("?")[0]
                            elif "gum.co/" in short:
                                slug_candidate = short.rsplit("/", 1)[-1]
                            if (target_product_id and pid == target_product_id) or (target_slug and slug_candidate == target_slug):
                                slug_local = slug_candidate
                                break
                        if slug_local:
                            edit_url = target_edit_url or f"https://gumroad.com/l/{slug_local}/edit"
                            await page.goto(edit_url, wait_until="domcontentloaded")
                            await asyncio.sleep(2)
                        return slug_local
                    except Exception:
                        return ""

                async def _open_product_from_products_page(preferred_name: str = "") -> str:
                    """On /products listing page, open first matching product edit page.

                    This is needed because Gumroad can bounce to /products after create flow.
                    """
                    try:
                        href = await page.evaluate(
                            """(preferredName) => {
                                const anchors = Array.from(document.querySelectorAll('a[href*="/products/"]'));
                                const filtered = anchors
                                  .map(a => ({href: a.getAttribute('href') || '', text: (a.textContent || '').trim()}))
                                  .filter(x => x.href && !x.href.includes('/products/new'));
                                if (!filtered.length) return '';
                                if (preferredName) {
                                  const m = filtered.find(x => x.text && x.text.toLowerCase().includes(preferredName.toLowerCase()));
                                  if (m) return m.href;
                                }
                                const edit = filtered.find(x => x.href.includes('/edit'));
                                if (edit) return edit.href;
                                return filtered[0].href;
                            }""",
                            preferred_name or "",
                        )
                    except Exception:
                        href = ""
                    if not href:
                        return ""
                    if href.startswith("/"):
                        href = f"https://gumroad.com{href}"
                    try:
                        await page.goto(href, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        # Normalize slug
                        if "/products/" in page.url:
                            slug_local = page.url.split("/products/")[-1].split("/")[0]
                            return slug_local
                    except Exception:
                        return ""
                    return ""

                async def _reopen_new_product_from_products_page() -> bool:
                    """Try to recover create flow when Gumroad redirects /products/new -> /products."""
                    try:
                        # Direct link first
                        href = await page.evaluate("""() => {
                            const direct = Array.from(document.querySelectorAll('a[href*="/products/new"]')).find(Boolean);
                            if (direct) return direct.getAttribute('href') || '';
                            const nodes = Array.from(document.querySelectorAll('a,button'));
                            for (const n of nodes) {
                                const text = (n.textContent || '').trim().toLowerCase();
                                if (text.includes('new product') || text.includes('create product') || text.includes('create')) {
                                    if (n.tagName.toLowerCase() === 'a') return n.getAttribute('href') || '';
                                }
                            }
                            return '';
                        }""")
                        if href:
                            if href.startswith("/"):
                                href = f"https://gumroad.com{href}"
                            await page.goto(href, wait_until="domcontentloaded")
                            await asyncio.sleep(2)
                            if "/products/new" in page.url or "/products/" in page.url:
                                return True
                        # Button fallback
                        for sel in [
                            'a:has-text("New product")',
                            'button:has-text("New product")',
                            'a:has-text("Create")',
                            'button:has-text("Create")',
                        ]:
                            try:
                                loc = page.locator(sel).first
                                if await loc.is_visible(timeout=1500):
                                    await loc.click()
                                    await asyncio.sleep(2)
                                    if "/products/new" in page.url or "/products/" in page.url:
                                        return True
                            except Exception:
                                continue
                    except Exception:
                        return False
                    return False

                async def _has_new_product_form() -> bool:
                    try:
                        name_ok = await page.locator('input[id^="name-"], input[placeholder^="Name"], input[name="name"]').count() > 0
                        price_ok = await page.locator('input[id^="price-"], input[placeholder*="Price"], input[name="price"]').count() > 0
                        next_ok = await page.locator('button[type="submit"][form^="new-product-form"], button:has-text("Next: Customize"), button:has-text("Next")').count() > 0
                        return bool(name_ok and (price_ok or next_ok))
                    except Exception:
                        return False

                async def _find_newly_created_draft() -> tuple[str, str]:
                    """Detect newly created listing by diffing products before/after create attempt."""
                    try:
                        existing = await self.get_products()
                        for prod in existing:
                            pid = str(prod.get("id") or "")
                            if not pid or pid in before_ids:
                                continue
                            if str(prod.get("name") or "").strip() != str(name).strip():
                                continue
                            short = prod.get("short_url", "") or prod.get("url", "")
                            slug_local = ""
                            if "/l/" in short:
                                slug_local = short.split("/l/")[-1].split("?")[0]
                            elif "gum.co/" in short:
                                slug_local = short.rsplit("/", 1)[-1]
                            if slug_local:
                                return pid, slug_local
                    except Exception:
                        return "", ""
                    return "", ""

                if slug_from_api:
                    await page.goto(target_edit_url or f"https://gumroad.com/l/{slug_from_api}/edit", wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                else:
                    # Step 1: Create product (may hit daily limit)
                    logger.info("Gumroad: open new product page", extra={"event": "gumroad_new_product"})
                    await page.goto("https://gumroad.com/products/new", wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    # Explicitly detect expired auth before daily-limit heuristics.
                    if "gumroad.com/login" in (page.url or ""):
                        if auth_retry >= 2:
                            await br.close()
                            return {"platform": "gumroad", "status": "cookie_expired", "error": "Session refresh loop limit reached."}
                        await br.close()
                        ok = await self._ensure_session_cookie()
                        if not ok:
                            return {"platform": "gumroad", "status": "cookie_expired", "error": "Session cookie/storage_state expired."}
                        retried = dict(content or {})
                        retried["_auth_retry"] = auth_retry + 1
                        return await self._publish_via_browser(retried)
                    # Recover flaky redirects until new-product form is actually present.
                    if not await _has_new_product_form():
                        recovered_form = False
                        for _ in range(3):
                            if page.url.rstrip("/").endswith("/products"):
                                await _reopen_new_product_from_products_page()
                            if await _has_new_product_form():
                                recovered_form = True
                                break
                            await page.goto("https://gumroad.com/products/new", wait_until="domcontentloaded")
                            await asyncio.sleep(2)
                        if recovered_form:
                            logger.info("Gumroad: new product form recovered", extra={"event": "gumroad_new_form_recovered"})
                        elif not content.get("allow_existing_update"):
                            return {
                                "platform": "gumroad",
                                "status": "daily_limit",
                                "error": "new_product_form_unavailable",
                                "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                            }
                    # If redirected to products list and updates are not allowed, stop immediately
                    try:
                        if page.url.rstrip("/").endswith("/products") and not content.get("allow_existing_update"):
                            # Sometimes Gumroad creates draft but returns to list; detect and attach to that draft.
                            new_pid, new_slug = await _find_newly_created_draft()
                            if new_slug:
                                slug_from_api = new_slug
                                product_id = new_pid
                                await page.goto(f"https://gumroad.com/products/{new_slug}/edit", wait_until="domcontentloaded")
                                await asyncio.sleep(2)
                                logger.info("Gumroad: adopted newly created draft after list redirect", extra={"event": "gumroad_adopt_new_draft", "context": {"product_id": new_pid}})
                            else:
                                recovered = await _reopen_new_product_from_products_page()
                                if not recovered or page.url.rstrip("/").endswith("/products"):
                                    return {
                                        "platform": "gumroad",
                                        "status": "daily_limit",
                                        "error": "redirected_to_products_list_update_not_allowed",
                                        "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                                    }
                                logger.info("Gumroad: create flow recovered from /products redirect", extra={"event": "gumroad_recover_new_flow"})
                    except Exception:
                        pass
                    if "login" in page.url:
                        await br.close()
                        # Retry login and re-open
                        ok = await self._ensure_session_cookie()
                        if not ok:
                            return {"platform": "gumroad", "status": "cookie_expired", "error": "Session cookie expired."}
                        return await self._publish_via_browser(content)
                    try:
                        content_html = await page.content()
                        if "only create 10 products per day" in content_html:
                            logger.warning("Gumroad: daily limit reached", extra={"event": "gumroad_daily_limit"})
                            slug_from_api = await _open_existing_product(name, allow_update=allow_existing_update)
                            if not slug_from_api:
                                await br.close()
                                return {"platform": "gumroad", "status": "daily_limit", "error": "Daily limit reached; update_existing_not_allowed"}
                    except Exception:
                        pass
                    # If we got redirected to the products list, open an existing product
                    try:
                        if page.url.rstrip("/").endswith("/products"):
                            slug_from_api = await _open_existing_product(name, allow_update=allow_existing_update)
                            if not slug_from_api:
                                return {"platform": "gumroad", "status": "daily_limit", "error": "redirected_to_products_list_update_not_allowed", "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else ""}
                    except Exception:
                        pass

                # Ensure we are on Product tab before filling fields
                try:
                    prod_tab = page.locator('button:has-text("Product"), a:has-text("Product")').first
                    if await prod_tab.is_visible(timeout=2000):
                        await prod_tab.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

                # Select product type (prefer digital) for new product flow only
                try:
                    type_btn = page.locator('button[data-type="digital"]').first
                    if not await type_btn.is_visible(timeout=2000):
                        type_btn = page.locator('button[data-type="ebook"]').first
                    if await type_btn.is_visible(timeout=2000):
                        await type_btn.click()
                        await asyncio.sleep(1)
                        logger.info("Gumroad: type selected", extra={"event": "gumroad_type_selected"})
                except Exception:
                    pass

                # Fill name
                name_el = page.locator('input[id^="name-"], input[placeholder^="Name"]').first
                if await name_el.is_visible(timeout=5000):
                    await name_el.fill(name)
                    logger.info("Gumroad: name filled", extra={"event": "gumroad_name_filled"})
                    try:
                        Path("/tmp/gumroad_new.html").write_text(await page.content())
                        await page.screenshot(path="/tmp/gumroad_new.png", full_page=True)
                        logger.info("Gumroad: debug snapshot saved", extra={"event": "gumroad_debug_saved"})
                    except Exception:
                        pass

                # Fill price
                try:
                    price_el = page.locator('input[id*="price-cents"]:not([id*="suggested"]), input[id^="price-"], input[placeholder*="Price"]').first
                    if await price_el.is_visible(timeout=3000):
                        await price_el.fill(price)
                        try:
                            await price_el.press("Tab")
                        except Exception:
                            pass
                        current_price = (await price_el.input_value()).strip()
                        current_digits = "".join(ch for ch in current_price if ch.isdigit())
                        if current_digits != str(price):
                            await page.evaluate(
                                """(val) => {
                                    const els = Array.from(document.querySelectorAll('input[id*=\"price-cents\"]'))
                                      .filter(el => !(el.id || '').includes('suggested'));
                                    for (const el of els) {
                                        el.focus();
                                        el.value = String(val);
                                        el.dispatchEvent(new Event('input', { bubbles: true }));
                                        el.dispatchEvent(new Event('change', { bubbles: true }));
                                        el.blur();
                                    }
                                }""",
                                str(price),
                            )
                except Exception:
                    pass

                # Fill URL/slug if field exists
                generated_slug = str(content.get("slug") or "").strip()
                if not generated_slug:
                    import re
                    base = re.sub(r"[^a-z0-9\\-]+", "-", str(name).lower()).strip("-")
                    if not base:
                        base = "vito-product"
                    generated_slug = f"{base[:42]}-{int(asyncio.get_event_loop().time())}"
                try:
                    url_el = page.get_by_label("URL").first
                    if await url_el.is_visible(timeout=1500):
                        await url_el.click()
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Backspace")
                        await url_el.fill(generated_slug)
                except Exception:
                    try:
                        url_el = page.locator('input[name*="url"], input[placeholder*="URL"], input[placeholder*="url"]').first
                        if await url_el.is_visible(timeout=1500):
                            await url_el.click()
                            await page.keyboard.press("Control+a")
                            await page.keyboard.press("Backspace")
                            await url_el.fill(generated_slug)
                    except Exception:
                        pass

                # Click Next: Customize for new product flow
                for sel in NEXT_SELECTORS:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=3000):
                            await btn.click()
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        continue

                # Wait for product edit URL
                try:
                    await page.wait_for_url("**/products/**", timeout=10000)
                except Exception:
                    pass
                # Ensure we're on a specific product edit page, not products list.
                # Never fallback to existing listings unless owner explicitly allowed update.
                try:
                    if page.url.rstrip("/").endswith("/products"):
                        if allow_existing_update:
                            slug_from_api = await _open_product_from_products_page(name) or await _open_existing_product(name, allow_update=True)
                        else:
                            new_pid, new_slug = await _find_newly_created_draft()
                            if new_slug:
                                product_id = new_pid
                                slug_from_api = new_slug
                                await page.goto(f"https://gumroad.com/products/{new_slug}/edit", wait_until="domcontentloaded")
                                await asyncio.sleep(2)
                                logger.info("Gumroad: adopted draft after submit redirect", extra={"event": "gumroad_adopt_new_draft", "context": {"product_id": new_pid}})
                            else:
                                return {
                                    "platform": "gumroad",
                                    "status": "daily_limit",
                                    "error": "new_draft_not_created_no_existing_update_allowed",
                                    "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                                }
                    elif "/products/" not in page.url:
                        if allow_existing_update:
                            slug_from_api = await _open_existing_product(name, allow_update=True)
                        else:
                            return {
                                "platform": "gumroad",
                                "status": "error",
                                "error": "new_draft_not_created",
                                "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                            }
                    logger.info(f"Gumroad: page url {page.url}", extra={"event": "gumroad_page_url"})
                except Exception:
                    pass
                try:
                    if "/products/" in page.url:
                        Path("/tmp/gumroad_edit.html").write_text(await page.content())
                        await page.screenshot(path="/tmp/gumroad_edit.png", full_page=True)
                        logger.info("Gumroad: edit snapshot saved", extra={"event": "gumroad_edit_saved"})
                except Exception:
                    pass
                # Try to extract slug from edit page
                try:
                    slug = await page.evaluate("""() => {
                        const form = document.querySelector('form[data-id]');
                        if (form) return form.getAttribute('data-id');
                        const script = document.querySelector('script[data-component-name="ProductEditPage"]');
                        if (script) {
                            try {
                                const data = JSON.parse(script.textContent);
                                if (data && data.unique_permalink) return data.unique_permalink;
                            } catch(e) {}
                        }
                        return '';
                    }""") or ""
                except Exception:
                    slug = ""

                # Fill summary
                summary_el = page.locator('input[placeholder*="You\'ll get"]').first
                try:
                    if await summary_el.is_visible(timeout=3000):
                        await summary_el.fill(summary)
                        try:
                            await summary_el.press("Tab")
                        except Exception:
                            pass
                        val = await summary_el.input_value()
                        if not str(val or "").strip():
                            await summary_el.fill(summary)
                        logger.info("Gumroad: summary filled", extra={"event": "gumroad_summary_filled"})
                except Exception:
                    pass

                # Fill description
                desc_el = page.locator('[contenteditable="true"]').first
                try:
                    if await desc_el.is_visible(timeout=3000):
                        await desc_el.click()
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Backspace")
                        desc_lines = [ln for ln in description.strip().split("\n") if ln.strip()]
                        if not desc_lines:
                            desc_lines = [description.strip()]
                        for i, line in enumerate(desc_lines):
                            await page.keyboard.type(line, delay=1)
                            if i != len(desc_lines) - 1:
                                await page.keyboard.press("Enter")
                        # Verify + fallback set (Tiptap can ignore keyboard input intermittently in headless mode)
                        current_desc = (await desc_el.inner_text()).strip()
                        if len(current_desc) < min(24, max(1, len(description.strip()) // 5)):
                            await page.evaluate(
                                """(text) => {
                                    const el = document.querySelector('[contenteditable="true"]');
                                    if (!el) return;
                                    el.focus();
                                    el.innerHTML = '';
                                    const p = document.createElement('p');
                                    p.textContent = text;
                                    el.appendChild(p);
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    el.blur();
                                }""",
                                description.strip(),
                            )
                        try:
                            await page.keyboard.press("Tab")
                        except Exception:
                            pass
                        logger.info("Gumroad: description filled", extra={"event": "gumroad_description_filled"})
                except Exception:
                    pass

                # Save Product tab edits explicitly before moving to Share/Content tabs.
                try:
                    for sel in [
                        'button:has-text("Save changes")',
                        'button:has-text("Save and continue")',
                        'button:has-text("Save")',
                    ]:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await asyncio.sleep(2)
                            break
                except Exception:
                    pass

                # Upload cover/thumbnail early (before Share tab navigation)
                uploaded_assets = False
                try:
                    if cover_path and Path(cover_path).exists():
                        try:
                            await page.locator('text=Cover').first.scroll_into_view_if_needed()
                            await asyncio.sleep(1)
                        except Exception:
                            pass
                        cover_section = page.locator('text=Cover').first.locator('xpath=ancestor::div[1]')
                        cover_btn = cover_section.get_by_text("Upload images or videos", exact=False).first
                        if await cover_btn.is_visible(timeout=2000):
                            async with page.expect_file_chooser(timeout=5000) as fc:
                                await cover_btn.click()
                            chooser = await fc.value
                            await chooser.set_files(cover_path)
                            await asyncio.sleep(4)
                            uploaded_assets = True
                            logger.info("Gumroad: cover uploaded", extra={"event": "gumroad_cover_uploaded"})
                        else:
                            cover_input = page.locator('text=Cover').first.locator('xpath=following::input[@type=\"file\"][1]')
                            if await cover_input.count() > 0:
                                await cover_input.set_input_files(cover_path)
                                await asyncio.sleep(4)
                                uploaded_assets = True
                                logger.info("Gumroad: cover uploaded", extra={"event": "gumroad_cover_uploaded"})
                    if thumb_path and Path(thumb_path).exists():
                        try:
                            await page.locator('text=Thumbnail').first.scroll_into_view_if_needed()
                            await asyncio.sleep(1)
                        except Exception:
                            pass
                        thumb_section = page.locator('text=Thumbnail').first.locator('xpath=ancestor::div[1]')
                        thumb_btn = thumb_section.get_by_text("Upload", exact=False).first
                        if await thumb_btn.count() > 0:
                            async with page.expect_file_chooser(timeout=5000) as fc:
                                await thumb_btn.click()
                            chooser = await fc.value
                            await chooser.set_files(thumb_path)
                            await asyncio.sleep(4)
                            uploaded_assets = True
                            logger.info("Gumroad: thumb uploaded", extra={"event": "gumroad_thumb_uploaded"})
                        else:
                            thumb_input = page.locator('text=Thumbnail').first.locator('xpath=following::input[@type=\"file\"][1]')
                            if await thumb_input.count() > 0:
                                await thumb_input.set_input_files(thumb_path)
                                await asyncio.sleep(4)
                                uploaded_assets = True
                                logger.info("Gumroad: thumb uploaded", extra={"event": "gumroad_thumb_uploaded"})
                except Exception:
                    pass

                # Debug UI labels/inputs to locate category/tags fields
                try:
                    ui_dump = await page.evaluate("""() => {
                        const labels = Array.from(document.querySelectorAll('label')).map(l => ({
                            text: l.innerText?.trim() || '',
                            for: l.getAttribute('for') || ''
                        })).filter(x => x.text);
                        const inputs = Array.from(document.querySelectorAll('input,select,textarea')).map(el => ({
                            tag: el.tagName.toLowerCase(),
                            type: el.getAttribute('type') || '',
                            id: el.getAttribute('id') || '',
                            name: el.getAttribute('name') || '',
                            placeholder: el.getAttribute('placeholder') || '',
                            aria: el.getAttribute('aria-label') || '',
                            role: el.getAttribute('role') || '',
                        }));
                        return {labels, inputs};
                    }""")
                    Path("/tmp/gumroad_ui_dump.json").write_text(str(ui_dump)[:10000])
                    logger.info("Gumroad: UI dump saved", extra={"event": "gumroad_ui_dump"})
                except Exception:
                    pass

                # Try switch to Share tab to find tags/category
                try:
                    for sel in SHARE_TAB_SELECTORS:
                        share_tab = page.locator(sel).first
                        if await share_tab.is_visible(timeout=2000):
                            await share_tab.click()
                            await asyncio.sleep(2)
                            ui_dump2 = await page.evaluate("""() => {
                                const labels = Array.from(document.querySelectorAll('label')).map(l => ({
                                    text: (l.innerText||'').trim(),
                                    for: l.getAttribute('for')||''
                                })).filter(x=>x.text);
                                const inputs = Array.from(document.querySelectorAll('input,select,textarea')).map(el => ({
                                    tag: el.tagName.toLowerCase(),
                                    type: el.getAttribute('type')||'',
                                    id: el.getAttribute('id')||'',
                                    name: el.getAttribute('name')||'',
                                    placeholder: el.getAttribute('placeholder')||'',
                                    aria: el.getAttribute('aria-label')||'',
                                    role: el.getAttribute('role')||''
                                }));
                                return {labels, inputs};
                            }""")
                            Path("/tmp/gumroad_ui_dump_share.json").write_text(str(ui_dump2)[:10000])
                            logger.info("Gumroad: UI dump (share) saved", extra={"event": "gumroad_ui_dump_share"})
                            # Set category/tags via Share tab comboboxes with option selection from suggestions.
                            async def _select_combobox_option(combo, query: str) -> bool:
                                try:
                                    await combo.click()
                                    await asyncio.sleep(0.15)
                                    await combo.fill(query)
                                    await asyncio.sleep(0.8)
                                    options = page.locator('[role="option"]')
                                    if await options.count() > 0:
                                        preferred = page.get_by_role("option", name=query)
                                        if await preferred.count() > 0:
                                            await preferred.first.click(timeout=1800)
                                        else:
                                            await options.first.click(timeout=1800)
                                        await asyncio.sleep(0.25)
                                        return True
                                    await page.keyboard.press("Enter")
                                    return True
                                except Exception:
                                    return False
                            try:
                                combos = page.locator('input[role="combobox"]')
                                if await combos.count() >= 1:
                                    cat_ok = await _select_combobox_option(combos.nth(0), "Programming")
                                    if cat_ok:
                                        logger.info("Gumroad: category set (share)", extra={"event": "gumroad_category_share"})
                            except Exception:
                                pass
                            try:
                                combos = page.locator('input[role="combobox"]')
                                if await combos.count() >= 2:
                                    tag_cb = combos.nth(1)
                                    added = 0
                                    for tag in tags_cfg[:5]:
                                        if await _select_combobox_option(tag_cb, tag):
                                            added += 1
                                    if added:
                                        logger.info("Gumroad: tags set (share)", extra={"event": "gumroad_tags_share", "context": {"count": added}})
                            except Exception:
                                pass
                            # Save after share updates
                            try:
                                for sel_save in SAVE_SELECTORS:
                                    btn = page.locator(sel_save).first
                                    if await btn.is_visible(timeout=2000):
                                        await btn.click()
                                        await asyncio.sleep(3)
                                        break
                            except Exception:
                                pass
                            break
                except Exception:
                    pass

                # Extract product_id early (needed for taxonomy/tag updates)
                try:
                    product_id = await page.evaluate("""() => {
                        const el = document.querySelector('[data-product-id]') || document.querySelector('[data-productid]');
                        if (el) return el.getAttribute('data-product-id') || el.getAttribute('data-productid');
                        const meta = document.querySelector('meta[name="product-id"]');
                        if (meta) return meta.getAttribute('content');
                        const script = document.querySelector('script[data-component-name="ProductEditPage"]');
                        if (script) {
                            try {
                                const data = JSON.parse(script.textContent);
                                if (data && data.id) return data.id;
                            } catch(e) {}
                        }
                        return null;
                    }""") or ""
                except Exception:
                    product_id = ""
                if not product_id:
                    try:
                        import re
                        html = await page.content()
                        patterns = [
                            r'"product_id"\s*:\s*"([a-zA-Z0-9_\\-]{6,})"',
                            r'"productId"\s*:\s*"([a-zA-Z0-9_\\-]{6,})"',
                            r'"product"\s*:\s*\\{[^\\}]*"id"\s*:\s*"([a-zA-Z0-9_\\-]{6,})"',
                        ]
                        for pat in patterns:
                            m = re.search(pat, html)
                            if m:
                                product_id = m.group(1)
                                break
                    except Exception:
                        product_id = ""
                if product_id:
                    logger.info(f"Gumroad: product_id extracted {product_id}", extra={"event": "gumroad_product_id"})
                else:
                    logger.info("Gumroad: product_id not found", extra={"event": "gumroad_product_id_missing"})

                # Try set category/tags via UI first
                try:
                    await page.locator('text=Product info').first.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                except Exception:
                    pass
                try:
                    cat_input = page.get_by_label("Category").first
                    if await cat_input.is_visible(timeout=1500):
                        await cat_input.click()
                        await page.keyboard.type("Programming", delay=10)
                        await page.keyboard.press("Enter")
                        logger.info("Gumroad: category UI set", extra={"event": "gumroad_category_ui"})
                except Exception:
                    pass
                try:
                    tag_input = page.get_by_label("Tags").first
                    if await tag_input.is_visible(timeout=1500):
                        for tag in tags_cfg[:8]:
                            await tag_input.fill(tag)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(0.1)
                        logger.info("Gumroad: tags UI set", extra={"event": "gumroad_tags_ui"})
                except Exception:
                    pass

                # Try set category/tags via API (React UI is dynamic)
                taxonomy_id = taxonomy_id_cfg
                tags = tags_cfg
                async def _set_taxonomy_and_tags() -> bool:
                    try:
                        slug_local = slug or ""
                        res = await page.evaluate(
                            """async ({productId, slug, taxonomyId, tags}) => {
                                const token = document.querySelector('meta[name="csrf-token"]')?.content;
                                const url = slug ? `/products/${slug}` : `/products/${productId}`;
                                const payload = { product: { taxonomy_id: taxonomyId, tags } };
                                async function tryFetch(method, headers, body, urlOverride) {
                                    const resp = await fetch(urlOverride || url, {
                                        method,
                                        headers,
                                        body,
                                        credentials: "same-origin",
                                    });
                                    const text = await resp.text();
                                    return {status: resp.status, text: text.slice(0, 200)};
                                }
                                if (token) {
                                    let r = await tryFetch("PUT", {
                                        "Content-Type": "application/json",
                                        "X-CSRF-Token": token,
                                        "Accept": "application/json",
                                    }, JSON.stringify(payload));
                                    if (r.status >= 200 && r.status < 300) return {ok: true, via: "json_put", status: r.status};
                                    r = await tryFetch("PATCH", {
                                        "Content-Type": "application/json",
                                        "X-CSRF-Token": token,
                                        "Accept": "application/json",
                                    }, JSON.stringify(payload));
                                    if (r.status >= 200 && r.status < 300) return {ok: true, via: "json_patch", status: r.status};
                                }
                                const form = new URLSearchParams();
                                if (token) form.append("authenticity_token", token);
                                form.append("product[taxonomy_id]", taxonomyId);
                                tags.forEach(t => form.append("product[tags][]", t));
                                form.append("product[tags]", tags.join(","));
                                let r2 = await tryFetch("PATCH", {
                                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                                    "Accept": "text/html,application/json",
                                }, form.toString());
                                if (r2.status >= 200 && r2.status < 300) return {ok: true, via: "form_patch", status: r2.status};
                                r2 = await tryFetch("POST", {
                                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                                    "Accept": "text/html,application/json",
                                }, form.toString());
                                if (r2.status >= 200 && r2.status < 300) return {ok: true, via: "form_post", status: r2.status};
                                r2 = await tryFetch("PATCH", {
                                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                                    "Accept": "text/html,application/json",
                                }, form.toString(), slug ? `/products/${slug}/discover` : `/products/${productId}/discover`);
                                if (r2.status >= 200 && r2.status < 300) return {ok: true, via: "discover_patch", status: r2.status};
                                return {ok: false, status: r2.status, text: r2.text};
                            }""",
                            {"productId": product_id, "slug": slug_local, "taxonomyId": taxonomy_id, "tags": tags},
                        )
                        if res and res.get("ok"):
                            logger.info("Gumroad: taxonomy/tags set", extra={"event": "gumroad_tax_tags_set", "context": res})
                            return True
                        logger.warning("Gumroad: taxonomy/tags update failed", extra={"event": "gumroad_tax_tags_fail", "context": res})
                    except Exception:
                        pass
                    return False

                if product_id:
                    await _set_taxonomy_and_tags()

                # Ensure Product tab visible before uploads
                try:
                    product_tab = page.locator('button:has-text("Product"), a:has-text("Product")').first
                    if await product_tab.is_visible(timeout=2000):
                        await product_tab.click()
                        await asyncio.sleep(2)
                except Exception:
                    pass
                # Debug upload elements
                try:
                    upload_dump = await page.evaluate("""() => {
                        const nodes = Array.from(document.querySelectorAll('button, a, div, label, span'));
                        const uploads = nodes
                          .filter(el => /upload/i.test(el.textContent || ''))
                          .slice(0, 40)
                          .map(el => ({
                            text: (el.textContent || '').trim().slice(0, 80),
                            tag: el.tagName.toLowerCase(),
                            role: el.getAttribute('role') || '',
                            aria: el.getAttribute('aria-label') || '',
                            class: el.className || '',
                          }));
                        return uploads;
                    }""")
                    Path("/tmp/gumroad_upload_elements.json").write_text(str(upload_dump)[:12000])
                    inputs_dump = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('input[type=\"file\"]')).map(el => ({
                            id: el.id || '',
                            name: el.name || '',
                            accept: el.accept || '',
                            class: el.className || ''
                        }));
                    }""")
                    Path("/tmp/gumroad_file_inputs.json").write_text(str(inputs_dump)[:8000])
                except Exception:
                    pass

                # Upload cover + thumbnail (use file chooser if inputs are hidden)
                if not uploaded_assets:
                    try:
                        if cover_path and Path(cover_path).exists():
                            try:
                                await page.locator('text=Cover').first.scroll_into_view_if_needed()
                                await asyncio.sleep(1)
                            except Exception:
                                pass
                            # Try by text within cover section (button may be a div)
                            cover_section = page.locator('text=Cover').first.locator('xpath=ancestor::div[1]')
                            try:
                                html = await cover_section.evaluate("el => el.outerHTML")
                                Path("/tmp/gumroad_cover_section.html").write_text(html[:8000])
                            except Exception:
                                pass
                            cover_btn = cover_section.get_by_text("Upload images or videos", exact=False).first
                            try:
                                logger.info(
                                    f"Gumroad: cover btn count={await cover_section.get_by_text('Upload images or videos', exact=False).count()}",
                                    extra={"event": "gumroad_cover_btn_count"},
                                )
                            except Exception:
                                pass
                            if await cover_btn.is_visible(timeout=2000):
                                async with page.expect_file_chooser(timeout=5000) as fc:
                                    await cover_btn.click()
                                chooser = await fc.value
                                await chooser.set_files(cover_path)
                                await asyncio.sleep(4)
                                logger.info("Gumroad: cover uploaded", extra={"event": "gumroad_cover_uploaded"})
                            else:
                                cover_input = page.locator('text=Cover').first.locator('xpath=following::input[@type=\"file\"][1]')
                                if await cover_input.count() > 0:
                                    await cover_input.set_input_files(cover_path)
                                    await asyncio.sleep(4)
                                    logger.info("Gumroad: cover uploaded", extra={"event": "gumroad_cover_uploaded"})
                                else:
                                    # Fallback: first file input on page
                                    any_input = page.locator('input[type=\"file\"]').first
                                    if await any_input.count() > 0:
                                        await any_input.set_input_files(cover_path)
                                        await asyncio.sleep(4)
                                        logger.info("Gumroad: cover uploaded", extra={"event": "gumroad_cover_uploaded"})
                        if thumb_path and Path(thumb_path).exists():
                            thumb_label = page.locator('text=Thumbnail')
                            if await thumb_label.count() > 0:
                                try:
                                    await thumb_label.first.scroll_into_view_if_needed()
                                    await asyncio.sleep(1)
                                except Exception:
                                    pass
                                thumb_section = thumb_label.first.locator('xpath=ancestor::div[1]')
                                try:
                                    html = await thumb_section.evaluate("el => el.outerHTML")
                                    Path("/tmp/gumroad_thumb_section.html").write_text(html[:8000])
                                except Exception:
                                    pass
                                thumb_btn = thumb_section.get_by_text("Upload", exact=False).first
                                try:
                                    logger.info(
                                        f"Gumroad: thumb btn count={await thumb_section.get_by_text('Upload', exact=False).count()}",
                                        extra={"event": "gumroad_thumb_btn_count"},
                                    )
                                except Exception:
                                    pass
                                if await thumb_btn.count() > 0:
                                    async with page.expect_file_chooser(timeout=5000) as fc:
                                        await thumb_btn.click()
                                    chooser = await fc.value
                                    await chooser.set_files(thumb_path)
                                    await asyncio.sleep(4)
                                    logger.info("Gumroad: thumb uploaded", extra={"event": "gumroad_thumb_uploaded"})
                                else:
                                    thumb_input = thumb_label.first.locator('xpath=following::input[@type=\"file\"][1]')
                                    if await thumb_input.count() > 0:
                                        await thumb_input.set_input_files(thumb_path)
                                        await asyncio.sleep(4)
                                        logger.info("Gumroad: thumb uploaded", extra={"event": "gumroad_thumb_uploaded"})
                                    else:
                                        inputs = page.locator('input[type=\"file\"]')
                                        if await inputs.count() > 1:
                                            await inputs.nth(1).set_input_files(thumb_path)
                                            await asyncio.sleep(4)
                                            logger.info("Gumroad: thumb uploaded", extra={"event": "gumroad_thumb_uploaded"})
                            else:
                                inputs = page.locator('input[type=\"file\"]')
                                if await inputs.count() > 1:
                                    await inputs.nth(1).set_input_files(thumb_path)
                                    await asyncio.sleep(4)
                                    logger.info("Gumroad: thumb uploaded", extra={"event": "gumroad_thumb_uploaded"})
                    except Exception:
                        pass

                # Upload digital file + preview screenshots in Content tab.
                try:
                    if pdf_path and Path(pdf_path).exists():
                        content_tab = page.locator('button:has-text("Content"), a:has-text("Content")').first
                        try:
                            await content_tab.click()
                            await asyncio.sleep(2)
                        except Exception:
                            pass
                        files_for_upload = [str(pdf_path)] + gallery_paths[:2]
                        upload_done = False

                        async def _existing_files_live() -> set[str]:
                            out: set[str] = set()
                            try:
                                state_tmp = await page.evaluate("""() => {
                                    const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                                    if (!el) return null;
                                    try { return JSON.parse(el.textContent); } catch(e) { return null; }
                                }""")
                                if isinstance(state_tmp, dict):
                                    files = state_tmp.get("existing_files") or []
                                    if isinstance(files, list):
                                        for f in files:
                                            if isinstance(f, dict):
                                                name = str(f.get("file_name") or "").strip().lower()
                                                if name:
                                                    out.add(name)
                            except Exception:
                                pass
                            return out

                        before_files = await _existing_files_live()

                        # Path 1: editor menu Insert -> Computer files.
                        try:
                            insert_btn = page.locator('button:has-text("Insert")').first
                            if await insert_btn.is_visible(timeout=2000):
                                async with page.expect_file_chooser(timeout=7000) as fc:
                                    await insert_btn.click()
                                    computer_item = page.locator('[role="menuitem"]:has-text("Computer files"), button:has-text("Computer files"), label:has-text("Computer files")').first
                                    if await computer_item.is_visible(timeout=3000):
                                        await computer_item.click()
                                chooser = await fc.value
                                await chooser.set_files(files_for_upload)
                                await asyncio.sleep(5)
                        except Exception:
                            pass

                        # Path 2: direct file inputs in Content tab.
                        if not upload_done:
                            try:
                                all_inputs = page.locator('input[type="file"]')
                                c = await all_inputs.count()
                                for i in range(c):
                                    fi = all_inputs.nth(i)
                                    try:
                                        accept = (await fi.get_attribute("accept") or "").lower()
                                    except Exception:
                                        accept = ""
                                    # Prefer broad inputs (accept empty) and file-capable inputs.
                                    if (not accept) or ("pdf" in accept) or ("image" in accept) or ("*" in accept):
                                        try:
                                            await fi.set_input_files(files_for_upload)
                                            await asyncio.sleep(2)
                                        except Exception:
                                            continue
                            except Exception:
                                pass

                        # Path 3: Upload button chooser.
                        if not upload_done:
                            upload_btn = page.locator('button:has-text("Upload your files"), button:has-text("Upload files")').first
                            if await upload_btn.is_visible(timeout=5000):
                                try:
                                    async with page.expect_file_chooser(timeout=7000) as fc:
                                        await upload_btn.click()
                                    chooser = await fc.value
                                    await chooser.set_files(files_for_upload)
                                    await asyncio.sleep(5)
                                except Exception:
                                    pass

                        after_files = await _existing_files_live()
                        upload_done = bool(after_files and len(after_files) >= len(before_files))
                        if upload_done:
                            logger.info("Gumroad: content files uploaded", extra={"event": "gumroad_content_files_uploaded", "context": {"count": len(files_for_upload)}})
                            # Save directly on Content tab.
                            try:
                                bsave = page.get_by_role("button", name="Save changes")
                                if await bsave.count() > 0:
                                    await bsave.first.click()
                                    await asyncio.sleep(2)
                            except Exception:
                                pass
                        # Back to Product tab
                        try:
                            for sel in PRODUCT_TAB_SELECTORS:
                                product_tab = page.locator(sel).first
                                if await product_tab.is_visible(timeout=2000):
                                    await product_tab.click()
                                    await asyncio.sleep(2)
                                    break
                        except Exception:
                            pass
                except Exception:
                    pass

                # Save
                try:
                    for sel in SAVE_SELECTORS:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await asyncio.sleep(4)
                            logger.info("Gumroad: saved", extra={"event": "gumroad_saved"})
                            break
                except Exception:
                    pass
                # Reload + read product state from embedded JSON (confirm taxonomy/tags)
                try:
                    await page.reload(wait_until="networkidle")
                    await asyncio.sleep(2)
                except Exception:
                    pass
                # Gumroad may redirect to products list after save; return to the exact edit page for validation.
                try:
                    if slug and ("/products/" not in page.url or "/edit" not in page.url):
                        await page.goto(f"https://gumroad.com/products/{slug}/edit", wait_until="networkidle")
                        await asyncio.sleep(2)
                except Exception:
                    pass
                product_state: dict[str, Any] | None = None
                existing_files_after: list[str] = []
                product_pdf_count = 0
                product_image_count = 0
                try:
                    state_raw = await page.evaluate("""() => {
                        const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                        if (!el) return null;
                        try { return JSON.parse(el.textContent); } catch(e) { return null; }
                    }""")
                    if isinstance(state_raw, dict):
                        if isinstance(state_raw.get("product"), dict):
                            product_state = state_raw.get("product")
                        files = state_raw.get("existing_files") or []
                        if isinstance(files, list):
                            for f in files:
                                if not isinstance(f, dict):
                                    continue
                                fname = str(f.get("file_name") or "").strip()
                                if fname:
                                    existing_files_after.append(fname.lower())
                                attached_name = str(f.get("attached_product_name") or "").strip().lower()
                                current_name = str((product_state or {}).get("name") or "").strip().lower()
                                if current_name and attached_name and attached_name != current_name:
                                    continue
                                ext = str(f.get("extension") or "").strip().lower()
                                if ext == "pdf":
                                    product_pdf_count += 1
                                if ext in {"png", "jpg", "jpeg", "webp", "gif", "svg"}:
                                    product_image_count += 1
                        if product_state:
                            logger.info(
                                "Gumroad: product state",
                                extra={"event": "gumroad_product_state", "context": {
                                    "taxonomy_id": product_state.get("taxonomy_id"),
                                    "tags": product_state.get("tags"),
                                    "is_published": product_state.get("is_published"),
                                    "existing_files_count": len(existing_files_after),
                                }},
                            )
                except Exception:
                    pass

                # Validate that expected files are really attached in product state.
                upload_validation_error = ""
                try:
                    need_pdf = bool(pdf_path and Path(pdf_path).exists())
                    need_images = len([gp for gp in gallery_paths[:2] if Path(gp).exists()])
                    # Fallback check in Content tab if current state did not include files.
                    if (need_pdf or need_images) and not existing_files_after and slug:
                        await page.goto(f"https://gumroad.com/products/{slug}/edit/content", wait_until="networkidle")
                        await asyncio.sleep(2)
                        state_raw2 = await page.evaluate("""() => {
                            const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                            if (!el) return null;
                            try { return JSON.parse(el.textContent); } catch(e) { return null; }
                        }""")
                        if isinstance(state_raw2, dict):
                            files2 = state_raw2.get("existing_files") or []
                            if isinstance(files2, list):
                                current_name2 = str(((state_raw2.get("product") or {}).get("name") or "")).strip().lower()
                                for f in files2:
                                    if isinstance(f, dict):
                                        fname = str(f.get("file_name") or "").strip().lower()
                                        if fname:
                                            existing_files_after.append(fname)
                                        attached_name = str(f.get("attached_product_name") or "").strip().lower()
                                        if current_name2 and attached_name and attached_name != current_name2:
                                            continue
                                        ext = str(f.get("extension") or "").strip().lower()
                                        if ext == "pdf":
                                            product_pdf_count += 1
                                        if ext in {"png", "jpg", "jpeg", "webp", "gif", "svg"}:
                                            product_image_count += 1
                    missing_flags: list[str] = []
                    if need_pdf and product_pdf_count < 1:
                        missing_flags.append("pdf")
                    if need_images and product_image_count < need_images:
                        missing_flags.append("gallery")
                    if missing_flags:
                        upload_validation_error = f"missing_attached_types:{','.join(missing_flags)}"
                        logger.warning(
                            "Gumroad: expected attachment types missing",
                            extra={"event": "gumroad_upload_validate_fail", "context": {"missing": missing_flags, "pdf": product_pdf_count, "images": product_image_count}},
                        )
                except Exception:
                    pass

                # Validate discovery metadata after save.
                meta_validation_error = ""
                try:
                    if product_state:
                        tax = str(product_state.get("taxonomy_id") or "").strip()
                        tags_live = product_state.get("tags") or []
                        if not tax:
                            meta_validation_error = "taxonomy_not_set"
                        elif not isinstance(tags_live, list) or len(tags_live) < 1:
                            meta_validation_error = "tags_not_set"
                except Exception:
                    pass

                try:
                    logger.info(f"Gumroad: page url {page.url}", extra={"event": "gumroad_page_url"})
                except Exception:
                    pass
                # Stay unpublished while configuring, if requested.
                if keep_unpublished:
                    # Prefer true draft state while profile is still being configured.
                    try:
                        unpublish_btn = page.locator('button:has-text("Unpublish")').first
                        if await unpublish_btn.is_visible(timeout=2000):
                            await unpublish_btn.click()
                            await asyncio.sleep(2)
                    except Exception:
                        pass
                    # API fallback (some pages don't expose unpublish button).
                    disable_result: dict[str, Any] = {}
                    try:
                        if product_id:
                            disable_result = await self.disable_product(product_id)
                    except Exception:
                        pass
                    # Re-check publication state after unpublish attempt.
                    draft_confirmed = False
                    try:
                        product_state2 = await page.evaluate("""() => {
                            const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                            if (!el) return null;
                            try { return JSON.parse(el.textContent).product; } catch(e) { return null; }
                        }""")
                        if isinstance(product_state2, dict):
                            draft_confirmed = not bool(product_state2.get("is_published"))
                    except Exception:
                        pass
                    if not draft_confirmed and disable_result.get("status") == "draft":
                        draft_confirmed = True
                    public_url = f"https://gumroad.com/l/{slug}" if slug else ""
                    if not public_url and product_id:
                        try:
                            products = await self.get_products()
                            for prod in products:
                                if str(prod.get("id") or "") == str(product_id):
                                    public_url = str(prod.get("short_url") or "")
                                    break
                        except Exception:
                            pass
                    return {
                        "platform": "gumroad",
                        "status": "draft",
                        "product_id": product_id,
                        "url": public_url,
                        "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        "draft_confirmed": draft_confirmed,
                        "files_attached": existing_files_after,
                        "error": upload_validation_error or meta_validation_error,
                    }
                # Guard: if still on /products/new, do not claim success
                try:
                    if "/products/new" in page.url:
                        return {"platform": "gumroad", "status": "error", "error": "daily_limit_or_new_page", "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else ""}
                except Exception:
                    pass

                # Try publish via UI (avoid API-only dependency)
                publish_url = ""
                def _maybe_extract_public_url(html_text: str) -> str:
                    import re
                    m = re.search(r'https?://gum\\.co/[A-Za-z0-9]+', html_text)
                    if m:
                        return m.group(0)
                    m = re.search(r'https?://gumroad\\.com/l/[A-Za-z0-9_\\-]+', html_text)
                    if m:
                        return m.group(0)
                    return ""
                async def _try_publish_buttons() -> str:
                    for sel in PUBLISH_SELECTORS:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await asyncio.sleep(4)
                            try:
                                await page.wait_for_url("**/l/**", timeout=8000)
                            except Exception:
                                pass
                            if "/l/" in page.url:
                                return page.url
                            try:
                                html_now = await page.content()
                                url = _maybe_extract_public_url(html_now)
                                if url:
                                    return url
                            except Exception:
                                pass
                    return ""
                try:
                    publish_url = await _try_publish_buttons()
                    if publish_url:
                        logger.info("Gumroad: publish via UI", extra={"event": "gumroad_publish_ui_ok"})
                except Exception:
                    pass

                # Go to Content tab and upload PDF
                if pdf_path and Path(pdf_path).exists():
                    try:
                        for sel in CONTENT_TAB_SELECTORS:
                            content_tab = page.locator(sel).first
                            if await content_tab.is_visible(timeout=2000):
                                await content_tab.click()
                                await asyncio.sleep(3)
                                break
                    except Exception:
                        pass

                    upload_btn = page.locator('button:has-text("Upload your files")').first
                    try:
                        if await upload_btn.is_visible(timeout=5000):
                            async with page.expect_file_chooser(timeout=5000) as fc:
                                await upload_btn.click()
                            chooser = await fc.value
                            await chooser.set_files(pdf_path)
                            await asyncio.sleep(5)
                            logger.info("Gumroad: pdf uploaded", extra={"event": "gumroad_pdf_uploaded"})
                    except Exception:
                        pass

                    # Save content
                    try:
                        save2 = page.locator('button:has-text("Save")').first
                        await save2.click()
                        await asyncio.sleep(3)
                    except Exception:
                        pass

                    # Try publish again after content upload
                    if not publish_url:
                        try:
                            publish_url = await _try_publish_buttons()
                            if publish_url:
                                logger.info("Gumroad: publish via UI (post-content)", extra={"event": "gumroad_publish_ui_ok"})
                        except Exception:
                            pass

                slug = slug or (page.url.split("/products/")[-1].split("/")[0] if "/products/" in page.url else "")
                try:
                    await page.screenshot(path=str(PUBLISH_SHOT), full_page=True)
                    logger.info("Gumroad: screenshot captured", extra={"event": "gumroad_screenshot"})
                except Exception:
                    pass
                await br.close()

            async def _verify_public(url: str) -> bool:
                try:
                    session = await self._get_session()
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        return resp.status in (200, 302)
                except Exception:
                    return False

            if publish_url:
                if await _verify_public(publish_url):
                    return {
                        "platform": "gumroad",
                        "status": "published",
                        "url": publish_url,
                        "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                    }
                return {
                    "platform": "gumroad",
                    "status": "error",
                    "error": "publish_url_not_verified",
                    "url": publish_url,
                    "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                }

            # If we extracted product_id from UI, try enable via API directly
            if product_id:
                enable_result = await self.enable_product(product_id)
                if enable_result.get("status") == "published" and enable_result.get("url"):
                    if await _verify_public(enable_result.get("url")):
                        return {
                            "platform": "gumroad",
                            "status": "published",
                            "product_id": product_id,
                            "url": enable_result.get("url"),
                            "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        }
                    return {
                        "platform": "gumroad",
                        "status": "error",
                        "product_id": product_id,
                        "url": enable_result.get("url"),
                        "error": "enable_url_not_verified",
                        "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                    }
                return {
                    "platform": "gumroad",
                    "status": "draft",
                    "product_id": product_id,
                    "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                    "error": enable_result.get("error", "enable_failed"),
                }

            # If we have slug, check public URL
            if slug:
                public_url = f"https://gumroad.com/l/{slug}"
                try:
                    session = await self._get_session()
                    async with session.get(public_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status in (200, 302):
                            return {
                                "platform": "gumroad",
                                "status": "published",
                                "url": public_url,
                                "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                            }
                except Exception:
                    pass

            # Publish via API — MUST confirm product exists and publish succeeds
            products = await self.get_products()
            for prod in products:
                short_url = prod.get("short_url", "") or ""
                # For strict non-update mode, never match by name (prevents reporting old products).
                if allow_existing_update:
                    matched = (prod.get("name") == name) or (slug and slug in short_url)
                else:
                    matched = bool(slug and slug in short_url)
                if matched:
                    pid = prod.get("id")
                    if draft_only:
                        return {
                            "platform": "gumroad",
                            "status": "draft",
                            "product_id": pid,
                            "url": prod.get("short_url", ""),
                            "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        }
                    enable_result = await self.enable_product(pid)
                    if enable_result.get("status") == "published" and (enable_result.get("url") or prod.get("short_url")):
                        url = enable_result.get("url") or prod.get("short_url", "")
                        if await _verify_public(url):
                            return {
                                "platform": "gumroad",
                                "status": "published",
                                "product_id": pid,
                                "url": url,
                                "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                            }
                        return {
                            "platform": "gumroad",
                            "status": "error",
                            "product_id": pid,
                            "url": url,
                            "error": "enable_url_not_verified",
                            "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        }
                    return {
                        "platform": "gumroad",
                        "status": "draft",
                        "product_id": pid,
                        "url": prod.get("short_url", ""),
                        "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        "error": enable_result.get("error", "enable_failed"),
                    }

            if not slug:
                return {
                    "platform": "gumroad",
                    "status": "error",
                    "error": "draft_not_created",
                    "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                }
            # Fallback: draft created but not found via API — treat as failure (no proof)
            return {
                "platform": "gumroad",
                "status": "error",
                "error": "product_not_found_via_api",
                "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
            }

        except Exception as e:
            logger.error(f"Gumroad browser publish error: {e}", exc_info=True)
            return {"platform": "gumroad", "status": "error", "error": str(e)}

    async def enable_product(self, product_id: str) -> dict:
        """PUT /v2/products/{id}/enable — publish a draft product."""
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "gumroad", "status": "not_authenticated"}

        try:
            session = await self._get_session()
            async with session.put(
                f"{API_BASE}/products/{product_id}/enable",
                params=self._params(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.content_type and "json" in resp.content_type:
                    data = await resp.json()
                else:
                    text = await resp.text()
                    logger.warning(f"Gumroad enable unexpected: {resp.status} {text[:200]}")
                    return {"platform": "gumroad", "status": "error", "error": f"HTTP {resp.status}"}

                if resp.status == 200 and data.get("success"):
                    product = data.get("product", {})
                    logger.info(
                        f"Gumroad product published: {product.get('name')}",
                        extra={"event": "gumroad_enable_ok", "context": {"product_id": product_id}},
                    )
                    return {
                        "platform": "gumroad",
                        "status": "published",
                        "product_id": product_id,
                        "url": product.get("short_url", ""),
                    }
                error = data.get("message", str(resp.status))
                logger.warning(f"Gumroad enable failed: {error}", extra={"event": "gumroad_enable_fail"})
                return {"platform": "gumroad", "status": "error", "error": error}
        except Exception as e:
            logger.error(f"Gumroad enable error: {e}", extra={"event": "gumroad_enable_error"}, exc_info=True)
            return {"platform": "gumroad", "status": "error", "error": str(e)}

    async def disable_product(self, product_id: str) -> dict:
        """PUT /v2/products/{id}/disable — unpublish product back to draft."""
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "gumroad", "status": "not_authenticated"}

        try:
            session = await self._get_session()
            async with session.put(
                f"{API_BASE}/products/{product_id}/disable",
                params=self._params(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.content_type and "json" in resp.content_type:
                    data = await resp.json()
                else:
                    text = await resp.text()
                    logger.warning(f"Gumroad disable unexpected: {resp.status} {text[:200]}")
                    return {"platform": "gumroad", "status": "error", "error": f"HTTP {resp.status}"}

                if resp.status == 200 and data.get("success"):
                    product = data.get("product", {})
                    logger.info(
                        "Gumroad product unpublished",
                        extra={"event": "gumroad_disable_ok", "context": {"product_id": product_id}},
                    )
                    return {
                        "platform": "gumroad",
                        "status": "draft",
                        "product_id": product_id,
                        "url": product.get("short_url", ""),
                    }
                error = data.get("message", str(resp.status))
                logger.warning(f"Gumroad disable failed: {error}", extra={"event": "gumroad_disable_fail"})
                return {"platform": "gumroad", "status": "error", "error": error}
        except Exception as e:
            logger.error(f"Gumroad disable error: {e}", extra={"event": "gumroad_disable_error"}, exc_info=True)
            return {"platform": "gumroad", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """GET /v2/products → суммирует sales_count и sales_usd_cents."""
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "gumroad", "sales": 0, "revenue": 0.0}

        try:
            products = await self.get_products()
            total_sales = sum(p.get("sales_count", 0) for p in products)
            total_revenue_cents = sum(p.get("sales_usd_cents", 0) for p in products)
            analytics = {
                "platform": "gumroad",
                "sales": total_sales,
                "revenue": total_revenue_cents / 100.0,
                "products_count": len(products),
            }
            logger.info(
                f"Gumroad аналитика: {total_sales} продаж, ${total_revenue_cents / 100:.2f}",
                extra={"event": "gumroad_analytics_ok", "context": analytics},
            )
            return analytics
        except Exception as e:
            logger.error(f"Gumroad analytics error: {e}", extra={"event": "gumroad_analytics_error"}, exc_info=True)
            return {"platform": "gumroad", "sales": 0, "revenue": 0.0, "error": str(e)}

    async def get_products(self) -> list[dict]:
        """GET /v2/products → список продуктов."""
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return []

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/products",
                params=self._params(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("success"):
                    products = data.get("products", [])
                    logger.info(
                        f"Gumroad: {len(products)} продуктов",
                        extra={"event": "gumroad_products_ok", "context": {"count": len(products)}},
                    )
                    return products
                return []
        except Exception as e:
            logger.error(f"Gumroad products error: {e}", extra={"event": "gumroad_products_error"}, exc_info=True)
            return []

    async def health_check(self) -> bool:
        """Проверка доступности API."""
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
