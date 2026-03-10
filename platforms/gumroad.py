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
from modules.browser_runtime_launcher import launch_browser, resolve_browser_engine
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
from modules.human_browser import HumanBrowser
from modules.listing_optimizer import optimize_listing_payload

logger = get_logger("gumroad", agent="gumroad")
API_BASE = "https://api.gumroad.com/v2"
COOKIE_FILE = Path("/tmp/gumroad_cookie.txt")
LOGIN_SHOT = Path("/tmp/gumroad_login.png")
PUBLISH_SHOT = Path("/tmp/gumroad_publish.png")
STORAGE_STATE_FILE = PROJECT_ROOT / "runtime" / "gumroad_storage_state.json"


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
        self._human_browser = HumanBrowser(logger=logger)

    @staticmethod
    def _storage_state_path() -> Path:
        p = Path(str(getattr(settings, "GUMROAD_STORAGE_STATE_FILE", "runtime/gumroad_storage_state.json") or "runtime/gumroad_storage_state.json"))
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    def _browser_context_kwargs(self, *, include_storage: bool = True) -> dict[str, Any]:
        storage_state = self._storage_state_path()
        runtime_profile = {
            "service": "gumroad",
            "storage_state_path": str(storage_state if include_storage else ""),
            "persistent_profile_dir": str(PROJECT_ROOT / "runtime" / "browser_profiles" / "gumroad"),
            "screenshot_first_default": True,
            "anti_bot_humanize": True,
            "headless_preferred": True,
            "llm_navigation_allowed": True,
        }
        return self._human_browser.context_kwargs(
            runtime_profile,
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            locale=str(getattr(settings, "BROWSER_LOCALE", "en-US") or "en-US"),
            timezone_id=str(getattr(settings, "BROWSER_TIMEZONE_ID", "America/New_York") or "America/New_York"),
        )

    def _browser_profile(self, *, include_storage: bool = True) -> dict[str, Any]:
        profile = {
            "service": "gumroad",
            "headless_preferred": os.environ.get("VITO_BROWSER_HEADLESS", "1").lower() not in ("0", "false", "no"),
            "proxy": None,
        }
        profile.update(self._browser_context_kwargs(include_storage=include_storage))
        return profile

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
            name = str(content.get("name") or "Working Gumroad Draft").strip()
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

        def _remember_platform_lesson(result: dict[str, Any]) -> None:
            try:
                from memory.memory_manager import MemoryManager
                from modules.failure_memory import FailureMemory
                from modules.platform_knowledge import record_platform_lesson
                status = str(result.get("status") or "unknown").strip().lower()
                slug_val = str(result.get("slug") or "").strip()
                url_val = str(result.get("url") or "").strip()
                error_val = str(result.get("error") or "").strip()
                files = result.get("files_attached") or []
                text = (
                    f"Gumroad publish attempt on slug={slug_val or 'n/a'} "
                    f"finished with status={status}. "
                    f"URL={url_val or 'n/a'}. "
                    f"Error={error_val or 'none'}. "
                    f"Files={files[:12]}"
                )
                metadata = {
                    "type": "platform_lesson" if status in {"draft", "created", "published"} else "platform_failure",
                    "platform": "gumroad",
                    "source": "gumroad.publish",
                    "source_agent": "ecommerce_agent",
                    "block_type": "skill" if status in {"draft", "created", "published"} else "failure",
                    "task_family": "listing_publish",
                    "status": status,
                    "slug": slug_val,
                    "url": url_val,
                    "error": error_val,
                    "files_attached": files[:12],
                    "task_root_id": str(content.get("task_root_id") or ""),
                    "importance_score": 0.82 if status in {"draft", "created", "published"} else 0.9,
                }
                doc_id = (
                    f"lesson_gumroad_{slug_val}_{status}"
                    if slug_val else
                    f"lesson_gumroad_{status}_{int(time.time())}"
                )
                MemoryManager().store_knowledge(doc_id=doc_id, text=text, metadata=metadata)
                lesson_points: list[str] = []
                anti_points: list[str] = []
                if slug_val:
                    lesson_points.append("Reuse the same working draft by explicit slug/id instead of creating a new listing.")
                if any(str(x).lower().endswith(".pdf") or "playbook" in str(x).lower() for x in files):
                    lesson_points.append("Main PDF can be attached during the content/file flow and should be verified in product state.")
                if any("cover" in str(x).lower() for x in files):
                    lesson_points.append("Cover/preview media and the main product file must be treated as separate artifact channels.")
                if error_val == "tags_not_set":
                    anti_points.append("Simple click on tag suggestions is not sufficient; Gumroad tag widget needs explicit commit behavior.")
                if error_val.startswith("missing_attached_types"):
                    anti_points.append("Do not treat image uploads as proof that the main PDF product file is attached.")
                record_platform_lesson(
                    "gumroad",
                    status=status,
                    summary=f"Gumroad listing run finished with status={status}",
                    details=text,
                    url=url_val,
                    lessons=lesson_points,
                    anti_patterns=anti_points,
                    evidence={
                        "slug": slug_val,
                        "error": error_val,
                        "files_attached": files[:12],
                        "product_id": str(result.get('product_id') or ''),
                        "task_root_id": str(content.get("task_root_id") or ""),
                    },
                    source="gumroad.publish",
                )
                if status not in {"draft", "created", "published"} or error_val:
                    FailureMemory().record(
                        agent="ecommerce_agent",
                        task_type="gumroad_publish",
                        detail=text[:500],
                        error=error_val[:500] or status,
                    )
            except Exception:
                pass
        try:
            result = await asyncio.wait_for(self._publish_via_browser(content), timeout=180)
            # Record execution facts to prevent false success claims
            try:
                facts = ExecutionFacts()
                evidence = result.get("url") or result.get("screenshot_path", "")
                sig = str(content.get("signature", "")).strip()
                detail = f"gumroad sig={sig}" if sig else "gumroad"
                if str(content.get("task_root_id") or "").strip():
                    detail = f"{detail} task={str(content.get('task_root_id'))[:48]}"
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
            _remember_platform_lesson(result)
            if str(result.get("status") or "") in {"timeout", "error", "cookie_expired", "daily_limit"}:
                fb = await _fallback_existing_publish(str(result.get("error") or result.get("status") or "browser_publish_failed"))
                if fb is not None:
                    _remember_platform_lesson(fb)
                    return fb
            return result
        except asyncio.TimeoutError:
            logger.error("Gumroad publish timed out")
            _remember_platform_lesson({"status": "timeout", "error": "browser_publish_timeout", "platform": "gumroad"})
            fb = await _fallback_existing_publish("browser_publish_timeout")
            if fb is not None:
                _remember_platform_lesson(fb)
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
            _engine_name, engine_factory = resolve_browser_engine()
            playwright_inst = await engine_factory().start()
            try:
                br = await launch_browser(playwright_inst, profile=self._browser_profile(include_storage=False))
                ctx = await br.new_context(**self._browser_context_kwargs(include_storage=False))
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
                # Verify authenticated session before persisting cookie/state.
                try:
                    await page.goto("https://gumroad.com/settings/profile", wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    cur = (page.url or "").lower()
                    if "login" in cur or "sign_in" in cur:
                        await page.screenshot(path=str(LOGIN_SHOT), full_page=True)
                        await br.close()
                        logger.warning("Gumroad login verification failed")
                        return False
                except Exception:
                    pass
                cookies = await ctx.cookies()
                session_cookie = next((c for c in cookies if c.get("name") == "_gumroad_app_session"), None)
                if session_cookie:
                    COOKIE_FILE.write_text(session_cookie.get("value", "").strip())
                    # Persist full authenticated storage state for browser-only publish flow.
                    try:
                        storage_state = self._storage_state_path()
                        storage_state.parent.mkdir(parents=True, exist_ok=True)
                        await ctx.storage_state(path=str(storage_state))
                    except Exception:
                        pass
                    await page.screenshot(path=str(LOGIN_SHOT), full_page=True)
                    await br.close()
                    logger.info("Gumroad session cookie saved", extra={"event": "gumroad_cookie_saved"})
                    return True
                await page.screenshot(path=str(LOGIN_SHOT), full_page=True)
                await br.close()
                return False
            finally:
                await playwright_inst.stop()
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
        storage_state = self._storage_state_path()
        has_storage = False
        if storage_state.exists():
            try:
                parsed = json.loads(storage_state.read_text(encoding="utf-8"))
                cookies = parsed.get("cookies") if isinstance(parsed, dict) else None
                has_storage = bool(isinstance(cookies, list) and cookies)
            except Exception:
                has_storage = False
        if not cookie and not has_storage:
            # Try to refresh session automatically before hard-failing.
            ok = await self._ensure_session_cookie()
            if ok and COOKIE_FILE.exists():
                cookie = COOKIE_FILE.read_text().strip()
                has_storage = STORAGE_STATE_FILE.exists()
        if not cookie and not has_storage:
            logger.warning("No Gumroad session cookie/storage state.")
            return {
                "platform": "gumroad",
                "status": "need_cookie",
                "error": "No session cookie or storage_state.",
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

        name = content.get("name", "Working Product")
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
            _engine_name, engine_factory = resolve_browser_engine()
            playwright_inst = await engine_factory().start()
            try:
                # Use stable publish launcher for Gumroad wizard (single-process constrained mode
                # can break /products/new React flow and bounce to affiliated page).
                br = await launch_browser(playwright_inst, profile=self._browser_profile(include_storage=has_storage))
                if has_storage:
                    ctx = await br.new_context(**self._browser_context_kwargs(include_storage=True))
                else:
                    ctx = await br.new_context(**self._browser_context_kwargs(include_storage=False))
                # Avoid overriding valid storage-state session with possibly stale cookie.
                if cookie and not has_storage:
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
                if allow_existing_update and target_slug:
                    try:
                        direct_edit_url = f"https://gumroad.com/products/{target_slug}/edit"
                        await page.goto(direct_edit_url, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        if f"/products/{target_slug}/edit" in str(page.url or "") and "login" not in str(page.url or ""):
                            slug_from_api = target_slug
                            target_edit_url = direct_edit_url
                            logger.info(
                                "Gumroad: opened target draft by slug",
                                extra={"event": "gumroad_open_target_slug", "context": {"slug": target_slug}},
                            )
                    except Exception:
                        slug_from_api = ""
                        target_edit_url = ""

                if allow_existing_update and not slug_from_api:
                    try:
                        existing = await self.get_products()
                        if not existing:
                            if target_product_id or target_slug:
                                await br.close()
                                return {
                                    "platform": "gumroad",
                                    "status": "error",
                                    "error": "target_product_not_found",
                                }
                            allow_existing_update = False
                            target_product_id = ""
                            target_slug = ""
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
                                    target_edit_url = f"https://gumroad.com/products/{slug_from_api}/edit"
                                elif "gum.co/" in short:
                                    slug_from_api = short.rsplit("/", 1)[-1]
                                    target_edit_url = f"https://gumroad.com/products/{slug_from_api}/edit"
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
                            edit_url = target_edit_url or f"https://gumroad.com/products/{slug_local}/edit"
                            await page.goto(edit_url, wait_until="domcontentloaded")
                            await asyncio.sleep(2)
                        return slug_local
                    except Exception:
                        return ""

                async def _open_product_from_products_page(preferred_name: str = "", strict_name_match: bool = False) -> str:
                    """On /products listing page, open first matching product edit page.

                    This is needed because Gumroad can bounce to /products after create flow.
                    """
                    try:
                        href = await page.evaluate(
                            """(payload) => {
                                const preferredName = String(payload?.preferredName || '');
                                const strict = !!payload?.strict;
                                const anchors = Array.from(document.querySelectorAll('a[href*="/products/"]'));
                                const filtered = anchors
                                  .map(a => ({href: a.getAttribute('href') || '', text: (a.textContent || '').trim()}))
                                  .filter(x => x.href && !x.href.includes('/products/new'));
                                if (!filtered.length) return '';
                                if (preferredName) {
                                  const m = filtered.find(x => x.text && x.text.toLowerCase().includes(preferredName.toLowerCase()));
                                  if (m) return m.href;
                                  if (strict) return '';
                                }
                                if (strict) return '';
                                const edit = filtered.find(x => x.href.includes('/edit'));
                                if (edit) return edit.href;
                                return filtered[0].href;
                            }""",
                            {"preferredName": preferred_name or "", "strict": bool(strict_name_match)},
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
                            if "/products/affiliated" in page.url:
                                for sel2 in (
                                    'button:has-text("Create Gum")',
                                    'a:has-text("Create Gum")',
                                    'button:has-text("Create")',
                                    'a:has-text("Create")',
                                ):
                                    try:
                                        b2 = page.locator(sel2).first
                                        if await b2.is_visible(timeout=1800):
                                            await b2.click(timeout=2000)
                                            await asyncio.sleep(2)
                                            break
                                    except Exception:
                                        continue
                            if "/products/new" in page.url or await _has_new_product_form():
                                return True
                        # Button fallback
                        for sel in [
                            'a:has-text("New product")',
                            'button:has-text("New product")',
                        ]:
                            try:
                                loc = page.locator(sel).first
                                if await loc.is_visible(timeout=1500):
                                    await loc.click()
                                    await asyncio.sleep(2)
                                    if "/products/affiliated" in page.url:
                                        for sel2 in (
                                            'button:has-text("Create Gum")',
                                            'a:has-text("Create Gum")',
                                            'button:has-text("Create")',
                                            'a:has-text("Create")',
                                        ):
                                            try:
                                                b2 = page.locator(sel2).first
                                                if await b2.is_visible(timeout=1800):
                                                    await b2.click(timeout=2000)
                                                    await asyncio.sleep(2)
                                                    break
                                            except Exception:
                                                continue
                                    if "/products/new" in page.url or await _has_new_product_form():
                                        return True
                            except Exception:
                                continue
                    except Exception:
                        return False
                    return False

                async def _open_new_product_via_products_tab() -> bool:
                    """Force open '/products/new' from '/products' tab (avoids affiliated detour)."""
                    try:
                        await page.goto("https://gumroad.com/products", wait_until="domcontentloaded")
                        await asyncio.sleep(1.5)
                        href = await page.evaluate("""() => {
                            const a = Array.from(document.querySelectorAll('a[href*="/products/new"]')).find(Boolean);
                            return a ? (a.getAttribute('href') || '') : '';
                        }""")
                        if href:
                            if href.startswith("/"):
                                href = f"https://gumroad.com{href}"
                            await page.goto(href, wait_until="domcontentloaded")
                        else:
                            # direct fallback if anchor not detected
                            await page.goto("https://gumroad.com/products/new", wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        return bool("/products/new" in (page.url or "") or await _has_new_product_form())
                    except Exception:
                        return False

                async def _has_new_product_form() -> bool:
                    try:
                        cur_url = str(page.url or "").lower()
                        if "/products/" in cur_url and "/edit" in cur_url:
                            return False
                        name_ok = await page.locator('input[id^="name-"], input[placeholder^="Name"], input[name="name"]').count() > 0
                        price_ok = await page.locator('input[id^="price-"], input[placeholder*="Price"], input[name="price"]').count() > 0
                        next_ok = await page.locator('button[type="submit"][form^="new-product-form"], button:has-text("Next: Customize")').count() > 0
                        # New Gumroad UI often starts at product-type chooser on /products/new
                        # (without visible name/price inputs yet).
                        type_chooser_ok = False
                        if "/products/new" in cur_url:
                            type_chooser_ok = await page.locator(
                                'button:has-text("Digital product"), button:has-text("Bundle"), [data-type="digital"], [data-type="ebook"]'
                            ).count() > 0
                        if "/products/new" in cur_url:
                            return bool((name_ok and (price_ok or next_ok)) or type_chooser_ok)
                        # Outside explicit /products/new, require a real new-product form marker.
                        form_marker = await page.locator('form[id^="new-product-form"], button[type="submit"][form^="new-product-form"]').count() > 0
                        return bool(form_marker and name_ok and (price_ok or next_ok))
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

                async def _fast_create_draft() -> str:
                    """Fast create path for current Gumroad /products/new UI."""
                    try:
                        await page.goto("https://gumroad.com/products/new", wait_until="domcontentloaded")
                        await asyncio.sleep(1.5)
                    except Exception:
                        return ""
                    for sel, val in (
                        ('input[id^="name-"], input[placeholder^="Name"], input[name="name"]', name),
                        ('input[id^="price-"], input[placeholder*="Price"], input[name="price"]', price),
                    ):
                        try:
                            el = page.locator(sel).first
                            if await el.count() > 0:
                                await el.click(timeout=2000)
                                await el.fill(str(val), timeout=2500)
                        except Exception:
                            continue
                    clicked = False
                    for sel in NEXT_SELECTORS:
                        try:
                            btn = page.locator(sel).first
                            if await btn.count() > 0 and await btn.is_visible(timeout=1500):
                                await btn.click(timeout=2500)
                                clicked = True
                                break
                        except Exception:
                            continue
                    if not clicked:
                        return ""
                    await asyncio.sleep(2.0)
                    cur = str(page.url or "")
                    if "/products/" in cur and "/edit" in cur and "/products/affiliated" not in cur:
                        return cur.split("/products/")[-1].split("/")[0]
                    return ""

                if slug_from_api:
                    await page.goto(target_edit_url or f"https://gumroad.com/products/{slug_from_api}/edit", wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                else:
                    # Fast path first: simple create is often more stable than full recovery flow.
                    try:
                        fast_slug = await _fast_create_draft()
                    except Exception:
                        fast_slug = ""
                    if fast_slug:
                        slug_from_api = fast_slug
                        await page.goto(f"https://gumroad.com/products/{fast_slug}/edit", wait_until="domcontentloaded")
                        await asyncio.sleep(1.2)
                    else:
                        # Step 1: Create product (may hit daily limit)
                        logger.info("Gumroad: open new product page", extra={"event": "gumroad_new_product"})
                        await page.goto("https://gumroad.com/products/new", wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        # New Gumroad flow may land on /products/affiliated chooser; continue into real draft editor.
                        try:
                            if "/products/affiliated" in (page.url or ""):
                                opened = await _open_new_product_via_products_tab()
                                if not opened:
                                    await page.goto("https://gumroad.com/products/new", wait_until="domcontentloaded")
                                    await asyncio.sleep(2)
                        except Exception:
                            pass
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
                                # Some Gumroad layouts render new-product form inline on /products.
                                if await _has_new_product_form():
                                    logger.info("Gumroad: inline new-product form detected on /products", extra={"event": "gumroad_inline_new_form"})
                                else:
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
                                        if not recovered or (page.url.rstrip("/").endswith("/products") and not await _has_new_product_form()):
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
                                # If inline creation form is available, continue creation instead of falling back to existing products.
                                if not await _has_new_product_form():
                                    slug_from_api = await _open_existing_product(name, allow_update=allow_existing_update)
                                    if not slug_from_api:
                                        return {"platform": "gumroad", "status": "daily_limit", "error": "redirected_to_products_list_update_not_allowed", "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else ""}
                        except Exception:
                            pass

                is_edit_page = "/products/" in str(page.url or "") and "/edit" in str(page.url or "")

                # Bootstrap new-product wizard when form is shown on /products/new (or inline).
                try:
                    if (not is_edit_page) and (await _has_new_product_form() or "/products/new" in (page.url or "")):
                        await page.evaluate(
                            """(payload) => {
                                const nm = String(payload?.name || '').trim();
                                const pr = String(payload?.price || '').trim();
                                const nameEl =
                                  document.querySelector('input[id^="name-"]') ||
                                  document.querySelector('input[placeholder^="Name"]') ||
                                  document.querySelector('input[name="name"]');
                                if (nameEl && nm) {
                                  nameEl.focus();
                                  nameEl.value = nm;
                                  nameEl.dispatchEvent(new Event('input', { bubbles: true }));
                                  nameEl.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                                const digitalCard =
                                  document.querySelector('[data-type="digital"]') ||
                                  Array.from(document.querySelectorAll('button,div,a')).find((n) => {
                                    const t = (n.textContent || '').toLowerCase();
                                    return t.includes('digital product');
                                  });
                                if (digitalCard) {
                                  try { digitalCard.click(); } catch(_) {}
                                }
                                const priceEl =
                                  document.querySelector('input[id^="price-"]') ||
                                  document.querySelector('input[placeholder*="Price"]') ||
                                  document.querySelector('input[name="price"]');
                                if (priceEl && pr) {
                                  priceEl.focus();
                                  priceEl.value = pr;
                                  priceEl.dispatchEvent(new Event('input', { bubbles: true }));
                                  priceEl.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                                const nextBtn =
                                  document.querySelector('button[type="submit"][form^="new-product-form"]') ||
                                  Array.from(document.querySelectorAll('button,a')).find((n) => {
                                    const t = (n.textContent || '').toLowerCase();
                                    return t.includes('next: customize') || t === 'next';
                                  });
                                if (nextBtn) {
                                  try { nextBtn.click(); } catch(_) {}
                                  return true;
                                }
                                return false;
                            }""",
                            {"name": name, "price": price},
                        )
                        await asyncio.sleep(2)
                except Exception:
                    pass

                # Ensure we are on Product tab before filling fields
                try:
                    for sel in PRODUCT_TAB_SELECTORS:
                        prod_tab = page.locator(sel).first
                        if await prod_tab.is_visible(timeout=2000):
                            logger.info("Gumroad: before product tab click", extra={"event": "gumroad_before_product_tab", "context": {"url": str(page.url or ""), "selector": sel}})
                            await prod_tab.click()
                            await asyncio.sleep(1)
                            logger.info("Gumroad: after product tab click", extra={"event": "gumroad_after_product_tab", "context": {"url": str(page.url or ""), "selector": sel}})
                            break
                except Exception:
                    pass

                # Select product type (prefer digital) for new product flow only
                try:
                    if not is_edit_page:
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

                if not is_edit_page:
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
                    logger.info("Gumroad: before wait_for_url", extra={"event": "gumroad_before_wait_for_url", "context": {"url": str(page.url or "")}})
                    await page.wait_for_url("**/products/**", timeout=10000)
                    logger.info("Gumroad: after wait_for_url", extra={"event": "gumroad_after_wait_for_url", "context": {"url": str(page.url or "")}})
                except Exception:
                    pass
                # Ensure we're on a specific product edit page, not products list.
                # Never fallback to existing listings unless owner explicitly allowed update.
                try:
                    logger.info("Gumroad: ensure edit page start", extra={"event": "gumroad_ensure_edit_start", "context": {"url": str(page.url or "")}})
                    if "/products/affiliated" in (page.url or ""):
                        # Wrong branch (affiliate editor), return to product creation flow.
                        await page.goto("https://gumroad.com/products/new", wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                    if page.url.rstrip("/").endswith("/products"):
                        if allow_existing_update:
                            slug_from_api = await _open_existing_product(name, allow_update=True)
                        else:
                                new_pid, new_slug = await _find_newly_created_draft()
                                if new_slug:
                                    product_id = new_pid
                                    slug_from_api = new_slug
                                    await page.goto(f"https://gumroad.com/products/{new_slug}/edit", wait_until="domcontentloaded")
                                    await asyncio.sleep(2)
                                    logger.info("Gumroad: adopted draft after submit redirect", extra={"event": "gumroad_adopt_new_draft", "context": {"product_id": new_pid}})
                                else:
                                    # Never adopt a pre-existing listing by title similarity in create mode.
                                    recovered_new = await _open_new_product_via_products_tab()
                                    if not recovered_new:
                                        return {
                                            "platform": "gumroad",
                                            "status": "daily_limit",
                                            "error": "new_draft_not_created_no_existing_update_allowed",
                                            "url": str(page.url or ""),
                                            "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                                        }
                                    logger.info("Gumroad: recovered create form after products redirect", extra={"event": "gumroad_recovered_after_redirect"})
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
                                    try:
                                        await combo.press("Control+a")
                                        await combo.press("Backspace")
                                    except Exception:
                                        pass
                                    await combo.fill(query)
                                    await asyncio.sleep(1.1)
                                    options = page.locator('[role="option"]')
                                    if await options.count() > 0:
                                        try:
                                            await combo.press("ArrowDown")
                                            await asyncio.sleep(0.1)
                                            await combo.press("Enter")
                                        except Exception:
                                            preferred = page.get_by_role("option", name=query)
                                            if await preferred.count() > 0:
                                                await preferred.first.click(timeout=1800)
                                            else:
                                                await options.first.click(timeout=1800)
                                        await asyncio.sleep(0.25)
                                        return True
                                    return False
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
                                        try:
                                            await tag_cb.click()
                                            await asyncio.sleep(0.1)
                                            await tag_cb.press("Control+a")
                                            await tag_cb.press("Backspace")
                                        except Exception:
                                            pass
                                        await tag_cb.fill(tag)
                                        await asyncio.sleep(1.0)
                                        options = page.locator('[role="option"]')
                                        if await options.count() > 0:
                                            try:
                                                await tag_cb.press("ArrowDown")
                                                await asyncio.sleep(0.1)
                                                await tag_cb.press("Enter")
                                            except Exception:
                                                await options.first.click(timeout=1800)
                                            await asyncio.sleep(0.35)
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
                        added_tags = 0
                        for tag in tags_cfg[:5]:
                            await tag_input.click()
                            await tag_input.fill(tag)
                            await asyncio.sleep(1.0)
                            options = page.locator('[role="option"]')
                            if await options.count() <= 0:
                                continue
                            preferred = page.get_by_role("option", name=re.compile(re.escape(tag), re.I))
                            if await preferred.count() > 0:
                                await preferred.first.click(timeout=1800)
                            else:
                                await options.first.click(timeout=1800)
                            await asyncio.sleep(0.3)
                            added_tags += 1
                        if added_tags:
                            logger.info("Gumroad: tags UI set", extra={"event": "gumroad_tags_ui", "context": {"count": added_tags}})
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
                    for sel in PRODUCT_TAB_SELECTORS:
                        product_tab = page.locator(sel).first
                        if await product_tab.is_visible(timeout=2000):
                            await product_tab.click()
                            await asyncio.sleep(2)
                            break
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

                def _artifact_key(path_value: str | Path | None) -> str:
                    raw = str(path_value or "").strip()
                    if not raw:
                        return ""
                    p = Path(raw)
                    stem = p.stem or p.name
                    return stem.strip().lower()

                async def _existing_file_keys_live() -> set[str]:
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
                                    if not isinstance(f, dict):
                                        continue
                                    name = str(f.get("file_name") or "").strip().lower()
                                    if name:
                                        out.add(name)
                    except Exception:
                        pass
                    return out

                existing_file_keys = await _existing_file_keys_live()

                async def _product_media_state_live() -> tuple[bool, bool]:
                    has_cover = False
                    has_thumb = False
                    try:
                        state_tmp = await page.evaluate("""() => {
                            const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                            if (!el) return null;
                            try { return JSON.parse(el.textContent); } catch(e) { return null; }
                        }""")
                        if isinstance(state_tmp, dict):
                            product_tmp = state_tmp.get("product") or {}
                            covers_tmp = product_tmp.get("covers") or []
                            thumb_tmp = state_tmp.get("thumbnail") or {}
                            has_cover = isinstance(covers_tmp, list) and len(covers_tmp) > 0
                            has_thumb = isinstance(thumb_tmp, dict) and bool(str(thumb_tmp.get("url") or "").strip())
                    except Exception:
                        pass
                    return has_cover, has_thumb

                async def _upload_product_media_via_menu(button_text: str, file_path_value: str) -> bool:
                    try:
                        trigger = page.locator(f'button:has-text("{button_text}")').first
                        if not await trigger.is_visible(timeout=2000):
                            return False
                        await trigger.click(force=True)
                        await asyncio.sleep(1)
                        menu_input = page.locator('label:has-text("Computer files") input[type="file"]').first
                        if await menu_input.count() > 0:
                            await menu_input.set_input_files(file_path_value)
                            await asyncio.sleep(5)
                            return True
                    except Exception:
                        pass
                    return False

                # Upload cover + thumbnail (use menu/input fallbacks)
                if not uploaded_assets:
                    try:
                        has_cover_live, has_thumb_live = await _product_media_state_live()
                        cover_key = _artifact_key(cover_path)
                        if cover_path and Path(cover_path).exists() and not has_cover_live:
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
                            cover_uploaded = False
                            if await cover_btn.is_visible(timeout=2000):
                                cover_uploaded = await _upload_product_media_via_menu("Upload images or videos", str(cover_path))
                                if cover_uploaded:
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
                            existing_file_keys = await _existing_file_keys_live()
                            has_cover_live, has_thumb_live = await _product_media_state_live()
                        elif cover_key:
                            logger.info(
                                "Gumroad: skip duplicate cover upload",
                                extra={"event": "gumroad_cover_skip_duplicate", "context": {"artifact": cover_key, "has_cover_live": has_cover_live}},
                            )
                        thumb_key = _artifact_key(thumb_path)
                        if thumb_path and Path(thumb_path).exists() and not has_thumb_live:
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
                                    uploaded = False
                                    try:
                                        async with page.expect_file_chooser(timeout=5000) as fc:
                                            await thumb_btn.click()
                                        chooser = await fc.value
                                        await chooser.set_files(thumb_path)
                                        await asyncio.sleep(4)
                                        uploaded = True
                                    except Exception:
                                        uploaded = False
                                    if not uploaded:
                                        uploaded = await _upload_product_media_via_menu("Upload", str(thumb_path))
                                    if uploaded:
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
                            existing_file_keys = await _existing_file_keys_live()
                            has_cover_live, has_thumb_live = await _product_media_state_live()
                        elif thumb_key:
                            logger.info(
                                "Gumroad: skip duplicate thumbnail upload",
                                extra={"event": "gumroad_thumb_skip_duplicate", "context": {"artifact": thumb_key, "has_thumb_live": has_thumb_live}},
                            )
                    except Exception:
                        pass

                # Upload digital file + preview screenshots in Content tab.
                try:
                    if pdf_path and Path(pdf_path).exists():
                        try:
                            if slug:
                                await page.goto(f"https://gumroad.com/products/{slug}/edit/content", wait_until="networkidle")
                                await asyncio.sleep(2)
                            else:
                                for sel in CONTENT_TAB_SELECTORS:
                                    content_tab = page.locator(sel).first
                                    if await content_tab.is_visible(timeout=2000):
                                        await content_tab.click()
                                        await asyncio.sleep(2)
                                        break
                        except Exception:
                            pass
                        files_for_upload = [str(pdf_path)] + gallery_paths[:2]
                        try:
                            Path("/tmp/gumroad_content_tab.html").write_text(await page.content(), encoding="utf-8")
                        except Exception:
                            pass
                        upload_done = False
                        before_files = await _existing_file_keys_live()
                        pdf_key = _artifact_key(pdf_path)
                        missing_gallery = []
                        for gp in gallery_paths[:2]:
                            if not Path(gp).exists():
                                continue
                            gp_key = _artifact_key(gp)
                            if gp_key and gp_key in before_files:
                                logger.info(
                                    "Gumroad: skip duplicate gallery upload",
                                    extra={"event": "gumroad_gallery_skip_duplicate", "context": {"artifact": gp_key}},
                                )
                                continue
                            missing_gallery.append(str(gp))

                        if pdf_key and pdf_key in before_files:
                            upload_done = True
                            logger.info(
                                "Gumroad: skip duplicate pdf upload",
                                extra={"event": "gumroad_pdf_skip_duplicate", "context": {"artifact": pdf_key}},
                            )

                        # Path 1: toolbar uploader -> Computer files.
                        if not upload_done:
                            try:
                                upload_btn = page.get_by_role("button", name="Upload files").first
                                if await upload_btn.is_visible(timeout=3000):
                                    await upload_btn.click()
                                    uploader_menu = page.locator('[role="menu"][aria-label="Image and file uploader"]').first
                                    if await uploader_menu.is_visible(timeout=3000):
                                        upload_input = uploader_menu.locator('label[role="menuitem"] input[type="file"][name="file"]').first
                                        if await upload_input.count() > 0:
                                            await upload_input.set_input_files(str(pdf_path))
                                            await asyncio.sleep(6)
                                            try:
                                                await page.wait_for_function(
                                                    """() => {
                                                        const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                                                        if (!el) return false;
                                                        try {
                                                            const data = JSON.parse(el.textContent || '{}');
                                                            const files = Array.isArray(data?.existing_files) ? data.existing_files : [];
                                                            return files.some((f) => {
                                                                const ext = String(f?.extension || '').toLowerCase();
                                                                const name = String(f?.file_name || '').toLowerCase();
                                                                return ext === 'pdf' || name.endsWith('.pdf');
                                                            });
                                                        } catch (_) {
                                                            return false;
                                                        }
                                                    }""",
                                                    timeout=15000,
                                                )
                                            except Exception:
                                                pass
                            except Exception:
                                pass

                        # Path 1b: explicit "Computer files" chooser on content page.
                        if not upload_done:
                            try:
                                direct_input = page.locator('[role="menu"][aria-label="Image and file uploader"] label[role="menuitem"] input[type="file"][name="file"]').first
                                if await direct_input.count() > 0:
                                    await direct_input.set_input_files(str(pdf_path))
                                    await asyncio.sleep(6)
                                    try:
                                        await page.wait_for_function(
                                            """() => {
                                                const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                                                if (!el) return false;
                                                try {
                                                    const data = JSON.parse(el.textContent || '{}');
                                                    const files = Array.isArray(data?.existing_files) ? data.existing_files : [];
                                                    return files.some((f) => {
                                                        const ext = String(f?.extension || '').toLowerCase();
                                                        const name = String(f?.file_name || '').toLowerCase();
                                                        return ext === 'pdf' || name.endsWith('.pdf');
                                                    });
                                                } catch (_) {
                                                    return false;
                                                }
                                            }""",
                                            timeout=15000,
                                        )
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        if not upload_done:
                            for sel in (
                                'label:has-text("Computer files")',
                                'button:has-text("Computer files")',
                                'text=Computer files',
                            ):
                                try:
                                    target = page.locator(sel).first
                                    if await target.is_visible(timeout=1500):
                                        async with page.expect_file_chooser(timeout=7000) as fc:
                                            await target.click()
                                        chooser = await fc.value
                                        await chooser.set_files(str(pdf_path))
                                        await asyncio.sleep(6)
                                        break
                                except Exception:
                                    continue

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
                                    name_attr = (await fi.get_attribute("name") or "").lower()
                                    if (not accept) or ("pdf" in accept) or ("application/pdf" in accept) or ("*" in accept) or ("file" in name_attr):
                                        try:
                                            await fi.set_input_files(str(pdf_path))
                                            await asyncio.sleep(5)
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
                                    await chooser.set_files(str(pdf_path))
                                    await asyncio.sleep(5)
                                except Exception:
                                    pass

                        after_files = await _existing_file_keys_live()
                        upload_done = bool(pdf_key and pdf_key in after_files) or any(name.endswith(".pdf") for name in after_files)
                        # Optional gallery upload after main PDF is visible.
                        if upload_done and missing_gallery:
                            try:
                                for gp in missing_gallery:
                                    if not Path(gp).exists():
                                        continue
                                    try:
                                        upload_btn = page.get_by_role("button", name="Upload files").first
                                        if await upload_btn.is_visible(timeout=2000):
                                            await upload_btn.click()
                                            await asyncio.sleep(1)
                                        uploader_menu = page.locator('[role="menu"][aria-label="Image and file uploader"]').first
                                        if await uploader_menu.is_visible(timeout=2000):
                                            upload_input = uploader_menu.locator('label[role="menuitem"] input[type="file"][name="file"]').first
                                            if await upload_input.count() > 0:
                                                await upload_input.set_input_files(str(gp))
                                                await asyncio.sleep(3)
                                                continue
                                    except Exception:
                                        pass
                                    all_inputs = page.locator('input[type="file"]')
                                    c = await all_inputs.count()
                                    for i in range(c):
                                        fi = all_inputs.nth(i)
                                        try:
                                            accept = (await fi.get_attribute("accept") or "").lower()
                                        except Exception:
                                            accept = ""
                                        if "image" not in accept and accept:
                                            continue
                                        try:
                                            await fi.set_input_files(str(gp))
                                            await asyncio.sleep(2)
                                            break
                                        except Exception:
                                            continue
                            except Exception:
                                pass
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

                async def _read_product_edit_state() -> dict[str, Any] | None:
                    try:
                        return await page.evaluate("""() => {
                            const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                            if (!el) return null;
                            try { return JSON.parse(el.textContent); } catch(e) { return null; }
                        }""")
                    except Exception:
                        return None

                async def _rewrite_discovery_metadata_server_side() -> bool:
                    try:
                        state_full = await _read_product_edit_state()
                        if not isinstance(state_full, dict):
                            return False
                        product_full = state_full.get("product")
                        if not isinstance(product_full, dict):
                            return False
                        product_full = dict(product_full)
                        product_full["taxonomy_id"] = taxonomy_id_cfg
                        product_full["tags"] = list(tags_cfg)
                        res = await page.evaluate(
                            """async ({slug, product}) => {
                                const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
                                const urls = [`/links/${slug}`, `/links/${slug}.json`];
                                for (const url of urls) {
                                    try {
                                        const resp = await fetch(url, {
                                            method: 'POST',
                                            headers: {
                                                'Content-Type': 'application/json',
                                                'Accept': 'application/json, text/plain, */*',
                                                ...(token ? {'X-CSRF-Token': token} : {}),
                                            },
                                            credentials: 'same-origin',
                                            body: JSON.stringify({ product }),
                                        });
                                        const text = await resp.text();
                                        if (resp.ok) return {ok: true, url, status: resp.status, text: text.slice(0, 200)};
                                    } catch (_) {}
                                }
                                return {ok: false};
                            }""",
                            {"slug": slug, "product": product_full},
                        )
                        return bool(isinstance(res, dict) and res.get("ok"))
                    except Exception:
                        return False

                try:
                    state_raw = await _read_product_edit_state()
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
                                ext = str(f.get("extension") or "").strip().lower()
                                if (not ext) and fname and "." in fname:
                                    ext = fname.rsplit(".", 1)[-1].lower()
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
                        state_raw2 = await _read_product_edit_state()
                        if isinstance(state_raw2, dict):
                            files2 = state_raw2.get("existing_files") or []
                            if isinstance(files2, list):
                                for f in files2:
                                    if isinstance(f, dict):
                                        fname = str(f.get("file_name") or "").strip().lower()
                                        if fname:
                                            existing_files_after.append(fname)
                                        ext = str(f.get("extension") or "").strip().lower()
                                        if (not ext) and fname and "." in fname:
                                            ext = fname.rsplit(".", 1)[-1].lower()
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
                        if ((not tax) or not isinstance(tags_live, list) or len(tags_live) < 1) and slug:
                            try:
                                await page.goto(f"https://gumroad.com/products/{slug}/edit/share", wait_until="networkidle")
                                await asyncio.sleep(2)
                                share_state = await page.evaluate("""() => {
                                    const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                                    if (!el) return null;
                                    try { return JSON.parse(el.textContent).product; } catch(e) { return null; }
                                }""")
                                if isinstance(share_state, dict):
                                    product_state = share_state
                                    tax = str(product_state.get("taxonomy_id") or "").strip()
                                    tags_live = product_state.get("tags") or []
                            except Exception:
                                pass
                        if ((not tax) or not isinstance(tags_live, list) or len(tags_live) < 1) and slug:
                            repaired = await _rewrite_discovery_metadata_server_side()
                            if repaired:
                                try:
                                    await page.goto(f"https://gumroad.com/products/{slug}/edit/share", wait_until="networkidle")
                                    await asyncio.sleep(2)
                                    share_state2 = await page.evaluate("""() => {
                                        const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                                        if (!el) return null;
                                        try { return JSON.parse(el.textContent).product; } catch(e) { return null; }
                                    }""")
                                    if isinstance(share_state2, dict):
                                        product_state = share_state2
                                        tax = str(product_state.get("taxonomy_id") or "").strip()
                                        tags_live = product_state.get("tags") or []
                                except Exception:
                                    pass
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
                    if "/products/affiliated" in (page.url or "").lower():
                        return {
                            "platform": "gumroad",
                            "status": "error",
                            "error": "wrong_editor_route_affiliated",
                            "url": str(page.url or ""),
                            "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        }
                    if not draft_confirmed:
                        return {
                            "platform": "gumroad",
                            "status": "error",
                            "error": "draft_not_confirmed",
                            "id": product_id or slug or generated_slug,
                            "slug": slug or generated_slug,
                            "url": public_url,
                            "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        }
                    return {
                        "platform": "gumroad",
                        "status": "draft",
                        "product_id": product_id,
                        "id": product_id or slug or generated_slug,
                        "slug": slug or generated_slug,
                        "url": public_url,
                        "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        "draft_confirmed": draft_confirmed,
                        "files_attached": existing_files_after,
                        "main_file_attached": product_pdf_count >= 1,
                        "cover_confirmed": product_image_count >= 1,
                        "preview_confirmed": product_image_count >= 1,
                        "thumbnail_confirmed": bool(product_state.get("thumbnail")) if isinstance(product_state, dict) else False,
                        "tags_confirmed": not bool(meta_validation_error),
                        "image_count": product_image_count,
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
            finally:
                await playwright_inst.stop()

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
                        "files_attached": existing_files_after,
                        "main_file_attached": product_pdf_count >= 1,
                        "cover_confirmed": product_image_count >= 1,
                        "preview_confirmed": product_image_count >= 1,
                        "thumbnail_confirmed": bool(product_state.get("thumbnail")) if isinstance(product_state, dict) else False,
                        "tags_confirmed": not bool(meta_validation_error),
                        "image_count": product_image_count,
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
                            "files_attached": existing_files_after,
                            "main_file_attached": product_pdf_count >= 1,
                            "cover_confirmed": product_image_count >= 1,
                            "preview_confirmed": product_image_count >= 1,
                            "thumbnail_confirmed": bool(product_state.get("thumbnail")) if isinstance(product_state, dict) else False,
                            "tags_confirmed": not bool(meta_validation_error),
                            "image_count": product_image_count,
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
                        "id": product_id or slug or generated_slug,
                        "slug": slug or generated_slug,
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
                            "id": pid or slug or generated_slug,
                            "slug": slug or generated_slug,
                            "url": prod.get("short_url", ""),
                            "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                            "files_attached": existing_files_after,
                            "main_file_attached": product_pdf_count >= 1,
                            "cover_confirmed": product_image_count >= 1,
                            "preview_confirmed": product_image_count >= 1,
                            "thumbnail_confirmed": bool(product_state.get("thumbnail")) if isinstance(product_state, dict) else False,
                            "tags_confirmed": not bool(meta_validation_error),
                            "image_count": product_image_count,
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
                                "files_attached": existing_files_after,
                                "main_file_attached": product_pdf_count >= 1,
                                "cover_confirmed": product_image_count >= 1,
                                "preview_confirmed": product_image_count >= 1,
                                "thumbnail_confirmed": bool(product_state.get("thumbnail")) if isinstance(product_state, dict) else False,
                                "tags_confirmed": not bool(meta_validation_error),
                                "image_count": product_image_count,
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
                        "id": pid or slug or generated_slug,
                        "slug": slug or generated_slug,
                        "url": prod.get("short_url", ""),
                        "screenshot_path": str(PUBLISH_SHOT) if PUBLISH_SHOT.exists() else "",
                        "files_attached": existing_files_after,
                        "main_file_attached": product_pdf_count >= 1,
                        "cover_confirmed": product_image_count >= 1,
                        "preview_confirmed": product_image_count >= 1,
                        "thumbnail_confirmed": bool(product_state.get("thumbnail")) if isinstance(product_state, dict) else False,
                        "tags_confirmed": not bool(meta_validation_error),
                        "image_count": product_image_count,
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
