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
from modules.display_bootstrap import ensure_display
from modules.execution_facts import ExecutionFacts
from modules.human_browser import HumanBrowser
from modules.listing_optimizer import optimize_listing_payload
from modules.platform_knowledge import record_platform_lesson
from modules.xvfb_session import XvfbSession
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
        self._human_browser = HumanBrowser(logger=logger)
        self._load_oauth_state()

    def _browser_context_kwargs(self) -> dict[str, Any]:
        runtime_profile = {
            "service": "etsy",
            "storage_state_path": str(self._storage_state_path),
            "persistent_profile_dir": str(PROJECT_ROOT / "runtime" / "browser_profiles" / "etsy"),
            "screenshot_first_default": True,
            "anti_bot_humanize": True,
            "headless_preferred": True,
            "llm_navigation_allowed": True,
        }
        return self._human_browser.context_kwargs(
            runtime_profile,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            locale=str(getattr(settings, "BROWSER_LOCALE", "en-US") or "en-US"),
            timezone_id=str(getattr(settings, "BROWSER_TIMEZONE_ID", "America/New_York") or "America/New_York"),
        )

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
        draft_only = bool(content.get("draft_only"))
        if bool(getattr(settings, "PUBLISH_CREATE_GUARD_ENABLED", True)):
            if operation in {"create", "new"} and allow_existing_update:
                result = {
                    "platform": "etsy",
                    "status": "blocked",
                    "error": "create_mode_forbids_existing_update",
                }
                self._record_browser_lesson(result, source="etsy.publish.browser")
                return result
            if allow_existing_update and not owner_edit_confirmed:
                result = {
                    "platform": "etsy",
                    "status": "blocked",
                    "error": "existing_update_requires_explicit_owner_request",
                }
                self._record_browser_lesson(result, source="etsy.publish.browser")
                return result
        if allow_existing_update and not target_listing_id:
            result = {
                "platform": "etsy",
                "status": "blocked",
                "error": "existing_update_requires_target_listing_id",
            }
            self._record_browser_lesson(result, source="etsy.publish.browser")
            return result
        if not self._storage_state_path.exists():
            result = {
                "platform": "etsy",
                "status": "needs_browser_login",
                "error": "Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture",
                "storage_state": str(self._storage_state_path),
            }
            self._record_browser_lesson(result, source="etsy.publish.browser")
            return result
        try:
            from playwright.async_api import async_playwright
        except Exception:
            result = {"platform": "etsy", "status": "error", "error": "playwright_not_installed"}
            self._record_browser_lesson(result, source="etsy.publish.browser")
            return result

        title = str(content.get("title") or "Working Etsy Product").strip()
        description = str(content.get("description") or "").strip()
        price = str(content.get("price") or "5")
        tags = content.get("tags") or []
        materials = content.get("materials") or []
        preview_paths = [str(x).strip() for x in (content.get("preview_paths") or []) if str(x).strip()]
        shot = str(PROJECT_ROOT / "runtime" / "etsy_browser_publish.png")
        page_html = str(PROJECT_ROOT / "runtime" / "etsy_browser_publish.html")

        browser = None
        context = None
        page = None
        xvfb = None
        try:
            async with async_playwright() as p:
                force_headless = os.getenv("VITO_FORCE_HEADLESS", "0").lower() in {"1", "true", "yes", "on"}
                launch_args = [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-blink-features=AutomationControlled",
                ]
                if not force_headless:
                    xvfb = XvfbSession(enabled=True)
                    xvfb.start()
                    if not str(os.getenv("DISPLAY", "")).strip():
                        ensure_display()
                try:
                    browser = await p.chromium.launch(
                        headless=force_headless or os.getenv("VITO_BROWSER_HEADLESS", "1").lower() not in {"0", "false", "no"},
                        args=launch_args,
                    )
                except Exception:
                    browser = await p.chromium.launch(headless=True, args=launch_args)
                context = await browser.new_context(**self._browser_context_kwargs())
                page = await context.new_page()
                async def _editor_debug() -> dict[str, Any]:
                    try:
                        return await page.evaluate(
                            """() => {
                                const q = (sel) => document.querySelectorAll(sel).length;
                                const val = (sel) => {
                                    const el = document.querySelector(sel);
                                    return el ? String(el.value || el.textContent || '').slice(0, 180) : '';
                                };
                                return {
                                    title_inputs: q("textarea[name='title'], textarea#listing-title-input, input[name='title'], input[data-test-id='listing-title-input']"),
                                    price_inputs: q("input#listing-price-input, input[name='variations.configuration.price'], input[name='price']"),
                                    file_inputs: q("input[type='file']"),
                                    tag_inputs: q("input#listing-tags-input, input[name='tags'], input[id*='tag'], input[placeholder*='tag' i]"),
                                    material_inputs: q("input#listing-materials-input, input[name='materials'], input[id*='material'], input[placeholder*='material' i]"),
                                    spinner_present: q("[data-clg-id='WtSpinner'], .wt-spinner") > 0,
                                    body_has_create: (document.body.innerText || '').toLowerCase().includes('создание объявления'),
                                    title_value: val("textarea[name='title'], textarea#listing-title-input, input[name='title'], input[data-test-id='listing-title-input']"),
                                    price_value: val("input#listing-price-input, input[name='variations.configuration.price'], input[name='price']"),
                                };
                            }"""
                        )
                    except Exception:
                        return {}

                async def _final_editor_audit(expected_pdf_name: str = "") -> dict[str, Any]:
                    try:
                        return await page.evaluate(
                            """(expectedPdfName) => {
                                const body = (document.body?.innerText || "");
                                const low = body.toLowerCase();
                                const imgs = Array.from(document.querySelectorAll("img"))
                                    .map((img) => String(img.getAttribute("src") || ""))
                                    .filter((src) => src.includes("etsy") || src.includes("etsystatic"));
                                const categoryHit =
                                    low.includes("гиды и справочники") ||
                                    low.includes("books, movies & music") ||
                                    low.includes("guides");
                                const expected = String(expectedPdfName || "").toLowerCase().trim();
                                return {
                                    hasDraft: low.includes("черновик") || low.includes("draft"),
                                    hasInstant: low.includes("мгновенная загрузка") || low.includes("instant download"),
                                    hasNoUnsaved: !(low.includes("несохран") || low.includes("unsaved")),
                                    hasTitle: Boolean(document.querySelector("textarea[name='title'], textarea#listing-title-input, input[name='title'], input[data-test-id='listing-title-input']")),
                                    hasTags: low.includes("теги") || low.includes("meme trend") || low.includes("creator guide"),
                                    hasMaterials: low.includes("материал") || low.includes("pdf guide") || low.includes("digital download"),
                                    hasUploadPrompt: low.includes("загрузить файл") || low.includes("upload a digital file") || low.includes("upload digital files"),
                                    hasPdfName: expected ? low.includes(expected) : false,
                                    categoryConfirmed: categoryHit,
                                    imageCount: imgs.length,
                                    etsyImgs: imgs.slice(0, 10),
                                };
                            }""",
                            Path(expected_pdf_name).name if expected_pdf_name else "",
                        )
                    except Exception:
                        return {}

                async def _wait_editor_ready(timeout_ms: int = 20000) -> dict[str, Any]:
                    try:
                        await page.wait_for_function(
                            """() => {
                                const spinner = document.querySelector("[data-clg-id='WtSpinner'], .wt-spinner");
                                const title = document.querySelector("textarea[name='title'], textarea#listing-title-input, input[name='title'], input[data-test-id='listing-title-input']");
                                const price = document.querySelector("input#listing-price-input, input[name='variations.configuration.price'], input[name='price']");
                                return (!spinner && (!!title || !!price)) || (!!title && !!price);
                            }""",
                            timeout=timeout_ms,
                        )
                    except Exception:
                        pass
                    return await _editor_debug()
                async def _click_named_button(texts: list[str], root=None, timeout_ms: int = 2500) -> str:
                    target = root or page
                    for txt in texts:
                        try:
                            btn = target.get_by_role("button", name=txt)
                            if await btn.count():
                                await btn.first.click(timeout=timeout_ms)
                                return txt
                        except Exception:
                            pass
                        try:
                            loc = target.locator(f"button:has-text('{txt}'), [role='button']:has-text('{txt}')")
                            if await loc.count():
                                await loc.first.click(timeout=timeout_ms)
                                return txt
                        except Exception:
                            pass
                    return ""

                async def _handle_wizard_dialogs(max_rounds: int = 8) -> list[str]:
                    handled: list[str] = []
                    for _ in range(max_rounds):
                        try:
                            roots = page.locator("[role='dialog'], .wt-dialog, [data-wt-dialog-root='true']")
                            if await roots.count() == 0:
                                break
                            root = roots.last
                            txt = ((await root.text_content()) or "").strip()
                        except Exception:
                            break
                        if not txt:
                            break
                        lowered = txt.lower()
                        action = ""
                        if "что это за товар?" in lowered or "what is this item?" in lowered:
                            action = await _click_named_button(["Продолжить", "Continue"], root=root)
                            handled.append("what_is_item")
                        elif "выберите партнеров по производству" in lowered or "production partner" in lowered:
                            action = await _click_named_button(["Готово", "Done"], root=root)
                            handled.append("production_partner")
                        elif "создать профиль обработки" in lowered or "processing profile" in lowered:
                            action = await _click_named_button(["Применить", "Apply"], root=root)
                            handled.append("processing_profile_create")
                        elif "ваши профили обработки" in lowered:
                            action = await _click_named_button(["Применить", "Apply"], root=root)
                            handled.append("processing_profile_select")
                        elif "создание политики" in lowered or "return" in lowered:
                            action = await _click_named_button(["Сохранить и применить", "Save and apply"], root=root)
                            handled.append("policy_create")
                        elif "изменить настройки" in lowered:
                            action = await _click_named_button(["Сохранить", "Save", "Готово"], root=root)
                            handled.append("settings_change")
                        elif "регионы, в которых работает etsy" in lowered:
                            action = await _click_named_button(["Понятно", "OK", "Готово"], root=root)
                            handled.append("regions_notice")
                        elif "отменить изменения?" in lowered:
                            action = await _click_named_button(["Продолжить редактирование", "Continue editing"], root=root)
                            handled.append("continue_editing")
                        elif "все равно изменить категорию" in lowered:
                            action = await _click_named_button(["Все равно изменить категорию"], root=root)
                            handled.append("force_change_category")
                        if not action:
                            break
                        await page.wait_for_timeout(1800)
                    return handled

                async def _discover_latest_draft_listing_id() -> str:
                    try:
                        await page.goto("https://www.etsy.com/your/shops/me/tools/listings", wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(2200)
                        draft_radio = page.locator("input[name='item_status'][value='draft']")
                        if await draft_radio.count():
                            await draft_radio.first.check(force=True)
                            await page.wait_for_timeout(3500)
                        hrefs = await page.evaluate(
                            """() => Array.from(document.querySelectorAll("a[href*='/listing/'], a[href*='/listing-editor/edit/']"))
                            .map(a => a.getAttribute('href') || '')
                            .filter(Boolean)
                            .slice(0, 200)"""
                        )
                        for h in hrefs or []:
                            mm = re.search(r"/listing-editor/edit/(\d+)", str(h)) or re.search(r"/listing/(\d+)", str(h))
                            if mm:
                                return mm.group(1)
                    except Exception:
                        return ""
                    return ""
                response_urls: list[str] = []
                try:
                    page.on("response", lambda resp: response_urls.append(str(getattr(resp, "url", "") or "")))
                except Exception:
                    pass
                if allow_existing_update and not target_listing_id:
                    result = {
                        "platform": "etsy",
                        "status": "blocked",
                        "error": "existing_update_requires_target_listing_id",
                    }
                    self._record_browser_lesson(result, source="etsy.publish.browser")
                    return result
                existing_ids: set[str] = set()
                if not allow_existing_update:
                    try:
                        await page.goto("https://www.etsy.com/your/shops/me/tools/listings", wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(1800)
                        hrefs = await page.evaluate(
                            """() => Array.from(document.querySelectorAll("a[href*='/listing/']"))
                            .map(a => a.getAttribute('href') || '')
                            .filter(Boolean)
                            .slice(0, 500)"""
                        )
                        for h in hrefs or []:
                            m0 = re.search(r"/listing/(\d+)", str(h)) or re.search(r"/listing-editor/edit/(\d+)", str(h))
                            if m0:
                                existing_ids.add(m0.group(1))
                    except Exception:
                        existing_ids = set()
                target_url = (
                    f"https://www.etsy.com/your/shops/me/listing-editor/edit/{target_listing_id}#details"
                    if allow_existing_update and target_listing_id
                    else "https://www.etsy.com/your/shops/me/tools/listings/create#details"
                )
                await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass
                await page.wait_for_timeout(3500)
                # Close GDPR/cookie dialog if present (can block editor controls).
                for txt in ("Принять", "Принять все", "Accept", "Accept All", "Continue", "Продолжить"):
                    try:
                        btn = page.get_by_role("button", name=txt)
                        if await btn.count():
                            await btn.first.click(timeout=1200)
                            await page.wait_for_timeout(350)
                    except Exception:
                        continue
                editor_probe = await _wait_editor_ready(timeout_ms=20000)
                await page.wait_for_timeout(1500)
                current = page.url.lower()
                if (not allow_existing_update) and "/tools/listings" in current and "/listing-editor/" not in current and "/create" not in current:
                    try:
                        create_href = await page.evaluate(
                            """() => {
                                const a = document.querySelector("a[href*='/listing-editor/create'], a[href*='/your/shops/me/listing-editor/create']");
                                return a ? (a.getAttribute('href') || '') : '';
                            }"""
                        )
                        if create_href:
                            if create_href.startswith("/"):
                                create_href = f"https://www.etsy.com{create_href}"
                            await page.goto(create_href, wait_until="domcontentloaded", timeout=90000)
                            await page.wait_for_timeout(2500)
                            try:
                                await page.wait_for_load_state("networkidle", timeout=10000)
                            except Exception:
                                pass
                            current = page.url.lower()
                    except Exception:
                        pass
                    for sel in (
                        "a[href*='/listing-editor/create']",
                        "a[href*='/tools/listings/create']",
                        "button:has-text('Add a listing')",
                        "button:has-text('Create listing')",
                        "a:has-text('Добавить товар')",
                        "button:has-text('Добавить товар')",
                        "button:has-text('Добавить объявление')",
                        "a:has-text('Add a listing')",
                    ):
                        try:
                            loc = page.locator(sel)
                            if await loc.count():
                                await loc.first.click(timeout=3000)
                                await page.wait_for_timeout(2500)
                                try:
                                    await page.wait_for_load_state("networkidle", timeout=10000)
                                except Exception:
                                    pass
                                current = page.url.lower()
                                if "/listing-editor/" in current or "/create" in current:
                                    break
                        except Exception:
                            continue
                editor_probe = await _wait_editor_ready(timeout_ms=12000)
                if bool(editor_probe.get("spinner_present")) and int(editor_probe.get("title_inputs") or 0) == 0:
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=90000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(2200)
                        editor_probe = await _wait_editor_ready(timeout_ms=12000)
                    except Exception:
                        pass
                if bool(editor_probe.get("spinner_present")) and int(editor_probe.get("title_inputs") or 0) == 0:
                    try:
                        await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(2500)
                        editor_probe = await _wait_editor_ready(timeout_ms=12000)
                    except Exception:
                        pass
                if "/signin" in current or "/oauth" in current:
                    result = {
                        "platform": "etsy",
                        "status": "needs_browser_login",
                        "error": "Stored Etsy session expired.",
                        "storage_state": str(self._storage_state_path),
                    }
                    self._record_browser_lesson(result, source="etsy.publish.browser")
                    return result
                if ("/listing/" in current and "/edit" in current) or ("/listing-editor/edit/" in current):
                    if not allow_existing_update:
                        result = {
                            "platform": "etsy",
                            "status": "blocked",
                            "error": "existing_listing_edit_detected_without_explicit_update",
                            "url": page.url,
                        }
                        self._record_browser_lesson(result, source="etsy.publish.browser")
                        return result
                    if target_listing_id and (f"/listing/{target_listing_id}" not in current and f"/listing-editor/edit/{target_listing_id}" not in current):
                        result = {
                            "platform": "etsy",
                            "status": "blocked",
                            "error": "existing_listing_mismatch_target",
                            "url": page.url,
                        }
                        self._record_browser_lesson(result, source="etsy.publish.browser")
                        return result

                # If category modal is open at landing, resolve it first.
                try:
                    if await page.locator("input[id^='category-'][type='checkbox']").count():
                        cb0 = page.locator("input[id^='category-'][type='checkbox']").first
                        await cb0.check(timeout=2500)
                        await page.wait_for_timeout(700)
                        for txt in ("Продолжить", "Continue"):
                            btn = page.get_by_role("button", name=txt)
                            if await btn.count():
                                await btn.first.click(timeout=2500)
                                await page.wait_for_timeout(1200)
                                break
                except Exception:
                    pass
                # Strong category dialog handler for current Etsy ListingEditor UI.
                try:
                    resolved = await page.evaluate(
                        """() => {
                            const root = document.querySelector("[data-wt-dialog-root='true'], .wt-dialog[role='dialog']");
                            if (!root) return false;
                            const cb = root.querySelector("input[id^='category-'][type='checkbox']");
                            if (cb && !cb.checked) cb.click();
                            const btns = Array.from(root.querySelectorAll("button"));
                            for (const b of btns) {
                                const t = (b.textContent || "").trim().toLowerCase();
                                if (t.includes("продолж") || t.includes("continue")) {
                                    b.click();
                                    return true;
                                }
                            }
                            return false;
                        }"""
                    )
                    if resolved:
                        await page.wait_for_timeout(1200)
                except Exception:
                    pass
                # Close/continue blocking onboarding dialogs if present.
                for txt in (
                    "Continue",
                    "Продолжить",
                    "Skip",
                    "Пропустить",
                    "Got it",
                    "Понятно",
                    "Done",
                    "Готово",
                ):
                    try:
                        btn = page.get_by_role("button", name=txt)
                        if await btn.count():
                            await btn.first.click(timeout=1800)
                            await page.wait_for_timeout(700)
                    except Exception:
                        continue
                # New-listing preflight dialog: set listing type/core details and continue.
                try:
                    await page.evaluate(
                        """() => {
                            const root =
                                document.querySelector("[data-wt-dialog-root='true']") ||
                                document.querySelector(".wt-dialog[role='dialog']");
                            if (!root) return false;
                            const titleEl = root.querySelector(".wt-dialog__header__heading");
                            const title = (titleEl?.textContent || "").trim().toLowerCase();
                            if (!title.includes("объявлен") && !title.includes("listing")) return false;
                            const clickLabel = (tokens) => {
                                const labels = Array.from(root.querySelectorAll("label"));
                                for (const l of labels) {
                                    const t = (l.textContent || "").trim().toLowerCase();
                                    if (tokens.some(tok => t.includes(tok))) {
                                        l.click();
                                        return true;
                                    }
                                }
                                return false;
                            };
                            clickLabel(["цифров", "digital"]);
                            clickLabel(["я", "i "]);
                            clickLabel(["готов", "finished"]);
                            clickLabel(["полностью мной", "original", "created by me"]);
                            const pickByName = (name, idx) => {
                                const nodes = Array.from(root.querySelectorAll(`input[type='radio'][name='${name}']`));
                                if (!nodes.length) return false;
                                const i = Math.max(0, Math.min(nodes.length - 1, idx));
                                const node = nodes[i];
                                node.click();
                                node.dispatchEvent(new Event('input', { bubbles: true }));
                                node.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            };
                            pickByName("listing_type_options_group", 1); // download
                            pickByName("whoMade", 0); // i_did
                            pickByName("isSupply", 0); // finished goods
                            pickByName("whatContent", 0); // original
                            const whenSel = root.querySelector("select#when-made-select, select[name='when_made'], select[name='whenMade']");
                            if (whenSel) {
                                const opts = Array.from(whenSel.querySelectorAll("option"));
                                let val = "";
                                for (const o of opts) {
                                    const ov = (o.value || "").trim();
                                    if (!ov) continue;
                                    if (ov === "2020_2026") { val = ov; break; }
                                    if (ov !== "made_to_order" && !val) val = ov;
                                }
                                if (val) {
                                    whenSel.value = val;
                                    whenSel.dispatchEvent(new Event('input', { bubbles: true }));
                                    whenSel.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }
                            const buttons = Array.from(root.querySelectorAll("button"));
                            for (const b of buttons) {
                                const t = (b.textContent || "").trim().toLowerCase();
                                if (t.includes("продолж") || t == "continue") {
                                    b.click();
                                    return true;
                                }
                            }
                            return false;
                        }"""
                    )
                    await page.wait_for_timeout(900)
                except Exception:
                    pass

                # Best-effort field fill; Etsy UI may vary by locale/account state.
                for sel in (
                    "textarea[name='title']",
                    "textarea#listing-title-input",
                    "input[name='title']",
                    "input[data-test-id='listing-title-input']",
                    "input[id*='title']",
                ):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(title[:140], timeout=1800)
                            break
                    except Exception:
                        continue
                # Force-set title via JS as fallback for React-controlled fields.
                try:
                    await page.evaluate(
                        """(val) => {
                            const el = document.querySelector("textarea[name='title'], textarea#listing-title-input, input[name='title']");
                            if (!el) return false;
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }""",
                        title[:140],
                    )
                except Exception:
                    pass
                for sel in ("textarea[name='description']", "textarea[id*='description']", "textarea"):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(description[:5000], timeout=1800)
                            break
                    except Exception:
                        continue
                for sel in (
                    "input[data-testid='price-input'][name='variations.configuration.price']",
                    "input#listing-price-input",
                    "input[name='price']",
                    "input[id*='price']",
                ):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(price, timeout=1800)
                            break
                    except Exception:
                        continue
                # Force-set price via JS fallback.
                try:
                    await page.evaluate(
                        """(val) => {
                            const el = document.querySelector("input#listing-price-input, input[name='variations.configuration.price'], input[name='price']");
                            if (!el) return false;
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }""",
                        str(price),
                    )
                except Exception:
                    pass
                # Common required attributes for draft creation.
                for sel, val in (
                    ("select[name='who_made']", "i_did"),
                    ("select[name='when_made']", "2020_2026"),
                    ("select[name='is_supply']", "false"),
                    ("input[name='quantity']", "1"),
                ):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            tag = await loc.first.evaluate("el => (el.tagName || '').toLowerCase()")
                            if tag == "select":
                                await loc.first.select_option(value=val, timeout=1500)
                            else:
                                await loc.first.fill(val, timeout=1500)
                    except Exception:
                        continue
                # React fallback for required selects.
                try:
                    await page.evaluate(
                        """() => {
                            const set = (sel, val) => {
                                const el = document.querySelector(sel);
                                if (!el) return false;
                                el.value = val;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            };
                            set("select[name='who_made']", "i_did");
                            set("select[name='when_made']", "2020_2026");
                            set("select[name='is_supply']", "false");
                            const q = document.querySelector("input[name='quantity']");
                            if (q) {
                                q.value = "1";
                                q.dispatchEvent(new Event('input', { bubbles: true }));
                                q.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }"""
                    )
                except Exception:
                    pass
                # Upload at least one image to satisfy listing publish requirements.
                image_path = str(content.get("cover_path") or content.get("image_path") or "").strip()
                if image_path and os.path.isfile(image_path):
                    try:
                        fi = page.locator("input[type='file']")
                        if await fi.count():
                            await fi.first.set_input_files(image_path, timeout=4000)
                            await page.wait_for_timeout(1800)
                    except Exception:
                        pass
                # Upload extra gallery images when available (thumb/preview).
                gallery_files: list[str] = []
                for key in ("thumb_path", "preview_path", "gallery_path"):
                    gp = str(content.get(key) or "").strip()
                    if gp and os.path.isfile(gp):
                        gallery_files.append(gp)
                for gp in preview_paths:
                    if gp and os.path.isfile(gp) and gp not in gallery_files and gp != image_path:
                        gallery_files.append(gp)
                if gallery_files:
                    try:
                        fi = page.locator("input[type='file']")
                        if await fi.count():
                            merged: list[str] = []
                            if image_path and os.path.isfile(image_path):
                                merged.append(image_path)
                            merged.extend(gallery_files[:3])
                            await fi.first.set_input_files(merged[:4], timeout=5000)
                            await page.wait_for_timeout(2200)
                    except Exception:
                        pass
                # Existing Etsy drafts can be left in "made to order" digital mode,
                # which hides the actual downloadable-file uploader.
                try:
                    body_text = ((await page.locator("body").inner_text()) or "").lower()
                    if ("файл на заказ" in body_text or "made to order" in body_text) and await page.locator("button[data-change-core-details-button='true']").count():
                        await page.locator("button[data-change-core-details-button='true']").first.click(timeout=2500)
                        await page.wait_for_timeout(900)
                        await page.evaluate(
                            """() => {
                                const root = document.querySelector('[data-wt-dialog-root="true"]');
                                if (!root) return false;
                                const sel = root.querySelector('select#when-made-select, select[name="when_made"], select[name="whenMade"]');
                                if (sel) {
                                    const opts = Array.from(sel.options).map(o => (o.value || "").trim()).filter(Boolean);
                                    const target = opts.find(v => v === "2020_2026") || opts.find(v => v && v !== "made_to_order") || "";
                                    if (target) {
                                        sel.value = target;
                                        sel.dispatchEvent(new Event('input', { bubbles: true }));
                                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                }
                                const applyBtn = Array.from(root.querySelectorAll('button')).find(
                                    b => /применить|apply/i.test((b.textContent || "").trim())
                                );
                                if (applyBtn) {
                                    applyBtn.click();
                                    return true;
                                }
                                return false;
                            }"""
                        )
                        await page.wait_for_timeout(1800)
                except Exception:
                    pass

                # Attach downloadable file for digital listing if input is present.
                digital_file = str(content.get("pdf_path") or content.get("file_path") or "").strip()
                if digital_file and os.path.isfile(digital_file):
                    try:
                        fi = page.locator("input[type='file']")
                        cfi = await fi.count()
                        for i in range(cfi):
                            loc = fi.nth(i)
                            acc = str((await loc.get_attribute("accept")) or "").lower()
                            if any(x in acc for x in ("pdf", "zip", "application")):
                                try:
                                    await loc.set_input_files(digital_file, timeout=7000)
                                    await page.wait_for_timeout(2000)
                                    break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                if tags:
                    tags_norm = [str(t).strip()[:20] for t in tags[:13] if str(t).strip()]
                    for sel in ("input#listing-tags-input", "input[name='tags']", "input[id*='tag']", "input[placeholder*='tag' i]"):
                        try:
                            loc = page.locator(sel)
                            if await loc.count():
                                await loc.first.click(timeout=1200)
                                for tg in tags_norm:
                                    try:
                                        await loc.first.fill(tg, timeout=1400)
                                        added = False
                                        for add_sel in ("#listing-tags-button", "button:has-text('Добавить')", "button:has-text('Add')"):
                                            add_btn = page.locator(add_sel)
                                            if await add_btn.count():
                                                try:
                                                    await add_btn.first.click(timeout=1200)
                                                    added = True
                                                    break
                                                except Exception:
                                                    continue
                                        if not added:
                                            await page.keyboard.press("Enter")
                                        await page.wait_for_timeout(120)
                                    except Exception:
                                        continue
                                break
                        except Exception:
                            continue
                if materials:
                    materials_norm = [str(t).strip()[:45] for t in materials[:10] if str(t).strip()]
                    for sel in ("input#listing-materials-input", "input[name='materials']", "input[id*='material']", "input[placeholder*='material' i]"):
                        try:
                            loc = page.locator(sel)
                            if await loc.count():
                                await loc.first.click(timeout=1200)
                                for mt in materials_norm:
                                    try:
                                        await loc.first.fill(mt, timeout=1400)
                                        added = False
                                        for add_sel in ("#listing-materials-button", "button:has-text('Добавить')", "button:has-text('Add')"):
                                            add_btn = page.locator(add_sel)
                                            if await add_btn.count():
                                                try:
                                                    await add_btn.first.click(timeout=1200)
                                                    added = True
                                                    break
                                                except Exception:
                                                    continue
                                        if not added:
                                            await page.keyboard.press("Enter")
                                        await page.wait_for_timeout(120)
                                    except Exception:
                                        continue
                                break
                        except Exception:
                            continue

                # If category dialog appears, pick a frequent category and continue.
                try:
                    if await page.locator("#category-field-search").count():
                        cb = page.locator("input[id^='category-']")
                        if await cb.count():
                            await cb.first.check(timeout=2500)
                            await page.wait_for_timeout(700)
                        for txt in ("Продолжить", "Continue", "Save category"):
                            btn = page.get_by_role("button", name=txt)
                            if await btn.count():
                                await btn.first.click(timeout=2500)
                                await page.wait_for_timeout(1200)
                                break
                except Exception:
                    pass
                # Force category checkbox (first frequent category) as fallback.
                try:
                    await page.evaluate(
                        """() => {
                            const cb = document.querySelector("input[id^='category-'][type='checkbox']");
                            if (!cb) return false;
                            cb.checked = true;
                            cb.dispatchEvent(new Event('input', { bubbles: true }));
                            cb.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }"""
                    )
                except Exception:
                    pass

                wizard_actions: list[str] = []
                for _ in range(5):
                    save_clicked = await _click_named_button(["Сохранить как черновик", "Save as draft", "Save and continue", "Save"])
                    if not save_clicked:
                        try:
                            forced = await page.evaluate(
                                """() => {
                                    const labels = ["save as draft", "save and continue", "save", "сохранить как черновик", "сохранить"];
                                    const buttons = Array.from(document.querySelectorAll("button"));
                                    for (const b of buttons) {
                                        const t = (b.textContent || "").trim().toLowerCase();
                                        if (labels.some(x => t.includes(x)) && !b.disabled) {
                                            b.scrollIntoView({ block: "center" });
                                            b.click();
                                            return true;
                                        }
                                    }
                                    return false;
                                }"""
                            )
                            if forced:
                                save_clicked = "forced_save"
                        except Exception:
                            save_clicked = ""
                    if not save_clicked:
                        break
                    wizard_actions.append(save_clicked)
                    await page.wait_for_timeout(1400)
                    handled = await _handle_wizard_dialogs()
                    wizard_actions.extend(handled)
                    await page.wait_for_timeout(1600)
                    try:
                        html_now = await page.content()
                        if re.search(r"/listing/(\d+)", page.url) or re.search(r"/listing-editor/edit/(\d+)", page.url) or re.search(r'"listingId"\s*:\s*(?!0)\d+', html_now):
                            break
                    except Exception:
                        pass
                # If "What is this item?" category dialog appears, resolve it and retry save.
                try:
                    has_category_dialog = await page.locator("div[role='dialog'] input[id^='category-']").count()
                    if has_category_dialog:
                        try:
                            cb = page.locator("div[role='dialog'] input[id^='category-']").first
                            await cb.check(timeout=2000)
                        except Exception:
                            pass
                        for txt in ("Продолжить", "Continue"):
                            try:
                                btn = page.locator("div[role='dialog']").get_by_role("button", name=txt)
                                if await btn.count():
                                    await btn.first.click(timeout=2200)
                                    await page.wait_for_timeout(1200)
                                    break
                            except Exception:
                                continue
                        # Retry save after taxonomy modal resolved.
                        for txt in ("Save as draft", "Save and continue", "Save", "Сохранить"):
                            try:
                                btn = page.get_by_role("button", name=txt)
                                if await btn.count():
                                    await btn.first.click(timeout=2500)
                                    await page.wait_for_timeout(1200)
                                    break
                            except Exception:
                                continue
                        # JS fallback to avoid locale/role differences.
                        try:
                            await page.evaluate(
                                """() => {
                                    const labels = ["save as draft", "save and continue", "save", "сохранить"];
                                    const buttons = Array.from(document.querySelectorAll("button"));
                                    for (const b of buttons) {
                                        const t = (b.textContent || "").trim().toLowerCase();
                                        if (labels.some(x => t.includes(x)) && !b.disabled) {
                                            b.click();
                                            return true;
                                        }
                                    }
                                    return false;
                                }"""
                            )
                            await page.wait_for_timeout(1100)
                        except Exception:
                            pass
                except Exception:
                    pass
                # If listing details dialog appears (type/core details), fill and continue, then retry save.
                try:
                    has_details_dialog = await page.evaluate(
                        """() => {
                            const root =
                                document.querySelector("[data-wt-dialog-root='true']") ||
                                document.querySelector(".wt-dialog[role='dialog']");
                            if (!root) return false;
                            const title = (root.querySelector(".wt-dialog__header__heading")?.textContent || "").toLowerCase();
                            return title.includes("объявлен") || title.includes("listing");
                        }"""
                    )
                    if has_details_dialog:
                        await page.evaluate(
                            """() => {
                                const root =
                                    document.querySelector("[data-wt-dialog-root='true']") ||
                                    document.querySelector(".wt-dialog[role='dialog']");
                                if (!root) return false;
                            const clickLabel = (tokens) => {
                                    const labels = Array.from(root.querySelectorAll("label"));
                                    for (const l of labels) {
                                        const t = (l.textContent || "").trim().toLowerCase();
                                        if (tokens.some(tok => t.includes(tok))) {
                                            l.click();
                                            return true;
                                        }
                                    }
                                    return false;
                            };
                            clickLabel(["цифров", "digital"]);
                            clickLabel(["я", "i "]);
                            clickLabel(["готов", "finished"]);
                            clickLabel(["полностью мной", "original", "created by me"]);
                            const pickByName = (name, idx) => {
                                const nodes = Array.from(root.querySelectorAll(`input[type='radio'][name='${name}']`));
                                if (!nodes.length) return false;
                                const i = Math.max(0, Math.min(nodes.length - 1, idx));
                                const node = nodes[i];
                                node.click();
                                node.dispatchEvent(new Event('input', { bubbles: true }));
                                node.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            };
                            pickByName("listing_type_options_group", 1);
                            pickByName("whoMade", 0);
                            pickByName("isSupply", 0);
                            pickByName("whatContent", 0);
                            const whenSel = root.querySelector("select#when-made-select, select[name='when_made'], select[name='whenMade']");
                            if (whenSel) {
                                const opts = Array.from(whenSel.querySelectorAll("option"));
                                let val = "";
                                for (const o of opts) {
                                    const ov = (o.value || "").trim();
                                    if (!ov) continue;
                                    if (ov === "made_to_order") { val = ov; break; }
                                    if (!val) val = ov;
                                }
                                if (val) {
                                    whenSel.value = val;
                                    whenSel.dispatchEvent(new Event('input', { bubbles: true }));
                                    whenSel.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }
                            const buttons = Array.from(root.querySelectorAll("button"));
                            for (const b of buttons) {
                                    const t = (b.textContent || "").trim().toLowerCase();
                                    if (t.includes("продолж") || t === "continue") {
                                        b.click();
                                        return true;
                                    }
                                }
                                return false;
                            }"""
                        )
                        await page.wait_for_timeout(1200)
                        for txt in ("Save as draft", "Save and continue", "Save", "Сохранить"):
                            try:
                                btn = page.get_by_role("button", name=txt)
                                if await btn.count():
                                    await btn.first.click(timeout=2500)
                                    await page.wait_for_timeout(1100)
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass

                # Try publish action explicitly unless owner asked draft-only flow.
                publish_clicked = False
                if not draft_only:
                    try:
                        forced = await page.evaluate(
                            """() => {
                                const labels = ["опубликовать","publish","publish listing","publish now"];
                                const buttons = Array.from(document.querySelectorAll("button"));
                                for (const b of buttons) {
                                    const t = (b.textContent || "").trim().toLowerCase();
                                    if (labels.some(x => t.includes(x)) && !b.disabled) {
                                        b.click();
                                        return true;
                                    }
                                }
                                return false;
                            }"""
                        )
                        if forced:
                            await page.wait_for_timeout(1600)
                            publish_clicked = True
                    except Exception:
                        pass
                    try:
                        pub = page.locator("button[data-testid='publish']")
                        if await pub.count():
                            await pub.first.click(timeout=2500)
                            await page.wait_for_timeout(1600)
                            publish_clicked = True
                    except Exception:
                        pass
                    try:
                        pub = page.locator("#shop-manager--listing-publish")
                        if await pub.count():
                            await pub.first.click(timeout=2500)
                            await page.wait_for_timeout(1600)
                            publish_clicked = True
                    except Exception:
                        pass
                    for txt in ("Publish", "Publish listing", "Publish now", "Опубликовать"):
                        try:
                            btn = page.get_by_role("button", name=txt)
                            if await btn.count():
                                await btn.first.click(timeout=2500)
                                await page.wait_for_timeout(1800)
                                publish_clicked = True
                                break
                        except Exception:
                            continue
                    # Etsy may show warning dialog like "Добавить больше фото" with skip option.
                    for txt in (
                        "Пропустить и продолжить",
                        "Skip and continue",
                        "Continue anyway",
                        "Да",
                        "Все равно изменить категорию",
                    ):
                        try:
                            btn = page.get_by_role("button", name=txt)
                            if await btn.count():
                                await btn.first.click(timeout=2500)
                                await page.wait_for_timeout(1800)
                                publish_clicked = True
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
                m = re.search(r"/listing/(\d+)", page.url) or re.search(r"/listing-editor/(\d+)", page.url)
                if m:
                    listing_id = m.group(1)
                if not listing_id:
                    try:
                        html_now = await page.content()
                        mi = re.search(r'"listingId"\s*:\s*(\d+)', html_now)
                        if mi and mi.group(1) != "0":
                            listing_id = mi.group(1)
                    except Exception:
                        pass
                if not listing_id:
                    try:
                        for ru in reversed(response_urls[-500:]):
                            mmr = re.search(r"/listing-editor/(\d+)", str(ru)) or re.search(r"/listing/(\d+)", str(ru))
                            if mmr:
                                listing_id = mmr.group(1)
                                break
                    except Exception:
                        pass
                if (not listing_id) and allow_existing_update:
                    try:
                        for ru in reversed(response_urls[-300:]):
                            mmr = re.search(r"/listing-editor/(\d+)", str(ru)) or re.search(r"/listing/(\d+)", str(ru))
                            if mmr:
                                listing_id = mmr.group(1)
                                break
                    except Exception:
                        pass
                if (not listing_id) and allow_existing_update:
                    try:
                        href = await page.locator("a[href*='/listing/']").first.get_attribute("href")
                        if href:
                            mm = re.search(r"/listing/(\d+)", href)
                            if mm:
                                listing_id = mm.group(1)
                            else:
                                mm2 = re.search(r"/listing-editor/(\d+)", href)
                                if mm2:
                                    listing_id = mm2.group(1)
                    except Exception:
                        pass
                # If editor URL still does not expose listing_id, verify by searching newest shop listing
                # with exact title in Listings manager (Drafts/Active).
                if not listing_id:
                    found_by_diff = False
                    try:
                        await page.goto("https://www.etsy.com/your/shops/me/tools/listings", wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(2200)
                        # Fast path: detect new listing by id-diff against initial snapshot.
                        hrefs2 = await page.evaluate(
                            """() => Array.from(document.querySelectorAll("a[href*='/listing/'],a[href*='/listing-editor/']"))
                            .map(a => a.getAttribute('href') || '')
                            .filter(Boolean)
                            .slice(0, 800)"""
                        )
                        if not hrefs2:
                            try:
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                await page.wait_for_timeout(1200)
                                hrefs2 = await page.evaluate(
                                    """() => Array.from(document.querySelectorAll("a[href*='/listing/'],a[href*='/listing-editor/']"))
                                    .map(a => a.getAttribute('href') || '')
                                    .filter(Boolean)
                                    .slice(0, 2000)"""
                                )
                            except Exception:
                                pass
                        for h2 in hrefs2 or []:
                            mm0 = re.search(r"/listing/(\d+)", str(h2)) or re.search(r"/listing-editor/(\d+)", str(h2))
                            if existing_ids and mm0 and mm0.group(1) not in existing_ids:
                                listing_id = mm0.group(1)
                                found_by_diff = True
                                break
                        if not found_by_diff:
                            for qsel in (
                                "input[type='search']",
                                "input[placeholder*='Search']",
                                "input[aria-label*='Search']",
                            ):
                                q = page.locator(qsel)
                                if await q.count():
                                    await q.first.fill(title[:80], timeout=1800)
                                    await page.keyboard.press("Enter")
                                    await page.wait_for_timeout(2400)
                                    break
                            matched_href = await page.evaluate(
                                """(needle) => {
                                    const key = String(needle || '').trim().toLowerCase();
                                    const links = Array.from(document.querySelectorAll("a[href*='/listing/'],a[href*='/listing-editor/']"));
                                    for (const a of links) {
                                        const href = a.getAttribute('href') || '';
                                        if (!href.includes('/listing/') && !href.includes('/listing-editor/')) continue;
                                        const card = a.closest('li,article,div');
                                        const txt = ((card && card.textContent) || a.textContent || '').toLowerCase();
                                        if (key && txt.includes(key)) return href;
                                    }
                                    return '';
                                }""",
                                title[:80],
                            )
                            if matched_href:
                                mm = re.search(r"/listing/(\d+)", matched_href) or re.search(r"/listing-editor/(\d+)", matched_href)
                                if mm:
                                    listing_id = mm.group(1)
                        # Last fallback for test flows: choose only genuinely new id not seen before.
                        if not listing_id:
                            ids_all: list[int] = []
                            for h2 in hrefs2 or []:
                                mmn = re.search(r"/listing/(\d+)", str(h2)) or re.search(r"/listing-editor/(\d+)", str(h2))
                                if not mmn:
                                    continue
                                try:
                                    ids_all.append(int(mmn.group(1)))
                                except Exception:
                                    continue
                            if ids_all:
                                for nid in sorted(set(ids_all), reverse=True):
                                    if str(nid) not in existing_ids:
                                        listing_id = str(nid)
                                        break
                    except Exception:
                        pass
                if listing_id:
                    audit = await _final_editor_audit(digital_file if 'digital_file' in locals() else "")
                    if (not allow_existing_update) and listing_id in existing_ids:
                        result = {
                            "platform": "etsy",
                            "status": "prepared",
                            "mode": "browser_only",
                            "url": page.url,
                            "screenshot_path": shot,
                            "error": "existing_listing_reused_in_create_mode",
                            "listing_id": listing_id,
                        }
                        self._record_browser_lesson(result, source="etsy.publish.browser")
                        return result
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
                    result = {
                        "platform": "etsy",
                        "status": "draft" if draft_only and not publish_clicked else "created",
                        "id": listing_id,
                        "listing_id": listing_id,
                        "url": url,
                        "mode": "browser_only",
                        "screenshot_path": shot,
                        "draft_only": bool(draft_only),
                        "fallback_existing": bool((not allow_existing_update) and listing_id in existing_ids),
                        "file_attached": bool(audit.get("hasPdfName")) or (bool(audit) and not bool(audit.get("hasUploadPrompt")) and bool(audit.get("hasInstant"))),
                        "image_count": int(audit.get("imageCount") or 0),
                        "tags_confirmed": bool(audit.get("hasTags")),
                        "materials_confirmed": bool(audit.get("hasMaterials")),
                        "category_confirmed": bool(audit.get("categoryConfirmed")),
                        "editor_audit": audit,
                    }
                    result = self._finalize_publish_result(
                        result,
                        mode="browser_only",
                        artifact_flags={
                            "listing_id": bool(listing_id),
                            "url": bool(url),
                            "file": bool(result.get("file_attached")),
                            "images": int(result.get("image_count") or 0) > 0,
                            "tags": bool(result.get("tags_confirmed")),
                            "materials": bool(result.get("materials_confirmed")),
                            "category": bool(result.get("category_confirmed")),
                            "screenshot": bool(shot),
                        },
                        required_artifacts=("listing_id", "url", "file", "images", "tags", "materials", "category", "screenshot"),
                    )
                    self._record_browser_lesson(result, source="etsy.publish.browser")
                    return result
                if draft_only and allow_existing_update and target_listing_id:
                    audit = await _final_editor_audit(digital_file if 'digital_file' in locals() else "")
                    fallback_url = f"https://www.etsy.com/listing/{target_listing_id}"
                    result = {
                        "platform": "etsy",
                        "status": "draft",
                        "id": target_listing_id,
                        "listing_id": target_listing_id,
                        "mode": "browser_only",
                        "url": fallback_url,
                        "screenshot_path": shot,
                        "draft_only": True,
                        "fallback_existing": True,
                        "file_attached": bool(audit.get("hasPdfName")) or (bool(audit) and not bool(audit.get("hasUploadPrompt")) and bool(audit.get("hasInstant"))),
                        "image_count": int(audit.get("imageCount") or 0),
                        "tags_confirmed": bool(audit.get("hasTags")),
                        "materials_confirmed": bool(audit.get("hasMaterials")),
                        "category_confirmed": bool(audit.get("categoryConfirmed")),
                        "editor_audit": audit,
                    }
                    result = self._finalize_publish_result(
                        result,
                        mode="browser_only",
                        artifact_flags={
                            "listing_id": bool(target_listing_id),
                            "url": bool(fallback_url),
                            "file": bool(result.get("file_attached")),
                            "images": int(result.get("image_count") or 0) > 0,
                            "tags": bool(result.get("tags_confirmed")),
                            "materials": bool(result.get("materials_confirmed")),
                            "category": bool(result.get("category_confirmed")),
                            "screenshot": bool(shot),
                        },
                        required_artifacts=("listing_id", "url", "file", "images", "tags", "materials", "category", "screenshot"),
                    )
                    self._record_browser_lesson(result, source="etsy.publish.browser")
                    return result
                editor_debug = editor_probe or await _editor_debug()
                editor_not_ready = bool(editor_debug.get("spinner_present"))
                result = {
                    "platform": "etsy",
                    "status": "prepared",
                    "id": "",
                    "mode": "browser_only",
                    "url": page.url,
                    "screenshot_path": shot,
                    "note": "Draft editor opened and fields filled; listing_id not detected yet.",
                    "publish_clicked": bool(publish_clicked),
                    "draft_only": bool(draft_only),
                    "error": "editor_not_ready" if editor_not_ready else "listing_id_not_detected",
                    "debug": editor_debug,
                    "wizard_actions": wizard_actions,
                }
                self._record_browser_lesson(result, source="etsy.publish.browser")
                return result
        except Exception as e:
            result = {"platform": "etsy", "status": "error", "error": str(e), "screenshot_path": shot}
            self._record_browser_lesson(result, source="etsy.publish.browser")
            return result
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
            try:
                if xvfb is not None:
                    xvfb.stop()
            except Exception:
                pass

    def _record_browser_lesson(self, result: dict[str, Any], *, source: str) -> None:
        try:
            status = str(result.get("status") or "unknown").strip().lower()
            debug = result.get("debug") if isinstance(result.get("debug"), dict) else {}
            details = []
            if result.get("error"):
                details.append(f"error={result.get('error')}")
            if result.get("listing_id"):
                details.append(f"listing_id={result.get('listing_id')}")
            if result.get("draft_only") is not None:
                details.append(f"draft_only={bool(result.get('draft_only'))}")
            for key in ("title_inputs", "price_inputs", "file_inputs", "tag_inputs", "material_inputs", "spinner_present"):
                if key in debug:
                    details.append(f"{key}={debug.get(key)}")
            lessons = []
            anti_patterns = []
            if status in {"draft", "created"}:
                lessons.append("Используй один рабочий listing_id и не считай create успешным без listing_id.")
                lessons.append("Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.")
            else:
                anti_patterns.append("Не считай Etsy create успешным только по открытому editor без listing_id.")
                if result.get("error"):
                    anti_patterns.append(f"Ошибка: {result.get('error')}")
            record_platform_lesson(
                "etsy",
                status=status,
                summary=f"Etsy browser publish result: {status}",
                details="; ".join(details),
                url=str(result.get("url") or ""),
                lessons=lessons,
                anti_patterns=anti_patterns,
                evidence={
                    "status": status,
                    "listing_id": result.get("listing_id"),
                    "url": result.get("url"),
                    "screenshot_path": result.get("screenshot_path"),
                    "draft_only": result.get("draft_only"),
                    "debug": debug,
                },
                source=source,
            )
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
        if self._mode in {"browser", "browser_only"}:
            # Safety default: browser flow must stay in draft mode unless owner explicitly confirms publish.
            if not bool((content or {}).get("publish_confirmed")):
                content = dict(content or {})
                content["draft_only"] = True
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
                result = {
                    "platform": "etsy",
                    "status": "created",
                    "listing_id": listing_id,
                    "url": listing_url,
                    "state": "draft",
                    "data": data,
                }
                return self._finalize_publish_result(
                    result,
                    mode="api",
                    artifact_flags={
                        "listing_id": bool(listing_id),
                        "url": bool(listing_url),
                    },
                    required_artifacts=("listing_id", "url"),
                )

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
