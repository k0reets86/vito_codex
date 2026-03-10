"""BrowserAgent — Agent 21: headless-браузер на Playwright.

Возможности: навигация, скриншоты, извлечение текста, формы, загрузка файлов.
Singleton: один инстанс Chromium на весь жизненный цикл.

OOM Protection:
- Singleton pattern: max 1 browser instance
- Reduced Chromium process pressure + --disable-dev-shm-usage flags
- Watchdog: kills orphan headless_shell processes (max 2 allowed)
- Memory limit: systemd MemoryMax=2G (RLIMIT_AS breaks V8/Node)
- Guaranteed cleanup in finally blocks
"""

import asyncio
import os
import platform
import random
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.resource_guard import resource_guard
from config.settings import settings
from modules.human_browser import HumanBrowser
from modules.browser_recovery_runtime import build_browser_recovery, build_form_fill_preflight, looks_like_selector
from modules.browser_runtime_policy import build_auth_interrupt_output, get_browser_runtime_profile

logger = get_logger("browser_agent", agent="browser_agent")

# --- OOM Protection Constants ---
MAX_HEADLESS_PROCESSES = 2
MEMORY_LIMIT_BYTES = 600 * 1024 * 1024  # 600 MB


def _set_memory_limit() -> None:
    """Log memory limit status.

    NOTE: RLIMIT_AS (virtual memory) kills Node.js/V8 which needs large virtual
    address space. Memory is instead limited by systemd MemoryMax=2G cgroup.
    """
    logger.info(
        "Memory limited by systemd cgroup (MemoryMax=2G), RLIMIT_AS skipped (breaks V8)",
        extra={"event": "memory_limit_info"},
    )


def _kill_orphan_headless_shells() -> int:
    """Kill orphan headless_shell/chrome processes exceeding MAX_HEADLESS_PROCESSES.

    Returns the number of processes killed.
    """
    if platform.system() != "Linux":
        return 0
    try:
        result = subprocess.run(
            ["pgrep", "-f", "headless_shell|chromium.*--headless"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in result.stdout.strip().split("\n") if p.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return 0

    if len(pids) <= MAX_HEADLESS_PROCESSES:
        return 0

    # Kill the oldest processes first (lowest PIDs), keep the newest ones
    pids_to_kill = sorted(pids)[:-MAX_HEADLESS_PROCESSES]
    killed = 0
    for pid in pids_to_kill:
        try:
            os.kill(pid, 9)  # SIGKILL
            killed += 1
            logger.warning(
                f"Killed orphan headless_shell pid={pid}",
                extra={"event": "orphan_process_killed", "pid": pid},
            )
        except OSError:
            pass  # Already dead

    if killed:
        logger.warning(
            f"Watchdog killed {killed} orphan headless_shell processes ({len(pids)} found, max {MAX_HEADLESS_PROCESSES})",
            extra={"event": "watchdog_cleanup", "killed": killed, "found": len(pids)},
        )
    return killed


def _chromium_launch_args() -> list[str]:
    base = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--disable-background-networking",
        "--renderer-process-limit=1",
        "--js-flags=--max-old-space-size=256",
    ]
    if bool(getattr(settings, "BROWSER_CONSTRAINED_MODE", True)):
        base.extend(["--no-zygote", "--single-process"])
    return base


def _browser_user_agent() -> str:
    explicit = str(getattr(settings, "BROWSER_USER_AGENT", "") or "").strip()
    if explicit:
        return explicit
    pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    ]
    return random.choice(pool)


def _stealth_init_script() -> str:
    return """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
window.chrome = window.chrome || { runtime: {} };
"""


class BrowserAgent(BaseAgent):
    NEEDS = {
        "browse": ["browser_runtime_policy", "auth_interrupt_policy"],
        "form_fill": ["browser_runtime_policy", "profile_completion_runbooks"],
        "register_with_email": ["browser_runtime_policy", "account_manager"],
        "*": ["browser_runtime_policy"],
    }

    _instance: Optional["BrowserAgent"] = None
    _browser = None
    _playwright_inst = None
    _lock: Optional[asyncio.Lock] = None
    _page_sem: Optional[asyncio.Semaphore] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        if hasattr(self, "_initialized"):
            return
        super().__init__(name="browser_agent", description="Headless-браузер: навигация, скриншоты, скрейпинг, формы", **kwargs)
        self._initialized = True
        self._context = None
        self._context_service = ""
        self._page = None
        self._human_browser = HumanBrowser(logger=logger)
        if BrowserAgent._lock is None:
            BrowserAgent._lock = asyncio.Lock()
        if BrowserAgent._page_sem is None:
            BrowserAgent._page_sem = asyncio.Semaphore(2)
        self._domain_last_action: dict[str, float] = {}
        self._domain_lock = asyncio.Lock()

    @property
    def capabilities(self) -> list[str]:
        return ["browse", "web_scrape", "form_fill", "register_with_email"]

    async def start(self) -> None:
        await super().start()
        lock = BrowserAgent._lock or asyncio.Lock()
        async with lock:
            if BrowserAgent._browser is not None and self._context is not None:
                return
            try:
                from playwright.async_api import async_playwright

                # Resource guard: проверяем есть ли RAM для Chromium (~300MB)
                if not resource_guard.can_proceed(estimated_mb=300):
                    logger.warning(
                        "Недостаточно RAM для запуска Chromium, пропускаю",
                        extra={"event": "browser_skip_low_ram"},
                    )
                    self._status = AgentStatus.IDLE
                    return

                # Watchdog: clean up orphan processes before launching
                _kill_orphan_headless_shells()

                last_error: Exception | None = None
                for attempt in range(1, 4):
                    try:
                        _set_memory_limit()
                        if BrowserAgent._playwright_inst is None:
                            BrowserAgent._playwright_inst = await async_playwright().start()
                        BrowserAgent._browser = await BrowserAgent._playwright_inst.chromium.launch(
                            headless=True,
                            args=_chromium_launch_args(),
                        )
                        context_kwargs = self._human_browser.context_kwargs(
                            self._runtime_profile(""),
                            user_agent=_browser_user_agent(),
                            locale=str(getattr(settings, "BROWSER_LOCALE", "en-US") or "en-US"),
                            timezone_id=str(getattr(settings, "BROWSER_TIMEZONE_ID", "America/New_York") or "America/New_York"),
                        )
                        self._context = await BrowserAgent._browser.new_context(**context_kwargs)
                        self._context_service = ""
                        if bool(getattr(settings, "BROWSER_STEALTH_ENABLED", True)):
                            await self._context.add_init_script(_stealth_init_script())
                        logger.info(
                            f"Playwright Chromium запущен (attempt={attempt})",
                            extra={"event": "browser_started", "context": {"attempt": attempt}},
                        )
                        return
                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"Playwright start attempt {attempt} failed: {str(e)[:240]}",
                            extra={"event": "browser_start_retry", "context": {"attempt": attempt}},
                        )
                        await self._force_cleanup()
                        _kill_orphan_headless_shells()
                        if attempt < 3:
                            await asyncio.sleep(float(attempt))
                raise last_error or RuntimeError("browser_start_failed")
            except Exception as e:
                self._status = AgentStatus.ERROR
                logger.error(f"Ошибка запуска Playwright: {e}", extra={"event": "browser_start_failed"}, exc_info=True)
                # Ensure cleanup on failed start
                await self._force_cleanup()

    async def _force_cleanup(self) -> None:
        """Force-close all browser resources. Used on error paths."""
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        self._context = None
        self._context_service = ""

        try:
            if BrowserAgent._browser:
                await BrowserAgent._browser.close()
        except Exception:
            pass
        BrowserAgent._browser = None

        try:
            if BrowserAgent._playwright_inst:
                await BrowserAgent._playwright_inst.stop()
        except Exception:
            pass
        BrowserAgent._playwright_inst = None

    async def stop(self) -> None:
        try:
            if self._context:
                await self._context.close()
                self._context = None
                self._context_service = ""
            if BrowserAgent._browser:
                await BrowserAgent._browser.close()
                BrowserAgent._browser = None
            if BrowserAgent._playwright_inst:
                await BrowserAgent._playwright_inst.stop()
                BrowserAgent._playwright_inst = None
        except Exception as e:
            logger.error(f"Ошибка остановки Playwright: {e}", extra={"event": "browser_stop_failed"})
            # Force cleanup even if graceful stop fails
            await self._force_cleanup()
        finally:
            BrowserAgent._instance = None
            if BrowserAgent._lock is not None:
                BrowserAgent._lock = None
            # Kill any remaining orphans after shutdown
            _kill_orphan_headless_shells()
            await super().stop()

    async def _ensure_browser(self, service: str = "") -> None:
        if BrowserAgent._browser is None or self._context is None:
            await self.start()
        if BrowserAgent._browser is None or self._context is None:
            raise RuntimeError("browser_unavailable")
        await self._ensure_service_context(service)

    async def _ensure_service_context(self, service: str = "") -> None:
        svc = str(service or "").strip().lower()
        if not svc or BrowserAgent._browser is None:
            return
        if self._context is not None and self._context_service == svc:
            return
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        profile = self._runtime_profile(svc)
        context_kwargs = self._human_browser.context_kwargs(
            profile,
            user_agent=_browser_user_agent(),
            locale=str(getattr(settings, "BROWSER_LOCALE", "en-US") or "en-US"),
            timezone_id=str(getattr(settings, "BROWSER_TIMEZONE_ID", "America/New_York") or "America/New_York"),
        )
        self._context = await BrowserAgent._browser.new_context(**context_kwargs)
        self._context_service = svc
        if bool(getattr(settings, "BROWSER_STEALTH_ENABLED", True)):
            await self._context.add_init_script(_stealth_init_script())

    async def _new_page(self, service: str = ""):
        sem = BrowserAgent._page_sem
        if sem is None:
            BrowserAgent._page_sem = asyncio.Semaphore(2)
            sem = BrowserAgent._page_sem
        async with sem:
            profile = self._runtime_profile(service)
            await self._ensure_browser(service)
            try:
                page = await self._context.new_page()
                await self._human_browser.prepare_page(page, profile=profile)
                return page
            except Exception:
                await self._force_cleanup()
                await self.start()
                await self._ensure_browser(service)
                page = await self._context.new_page()
                await self._human_browser.prepare_page(page, profile=profile)
                return page

    @staticmethod
    def _random_delay_ms(lo: int, hi: int) -> int:
        lo2 = int(min(lo, hi))
        hi2 = int(max(lo, hi))
        return random.randint(lo2, hi2)

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            return (urlparse(str(url or "")).netloc or "").lower().strip()
        except Exception:
            return ""

    async def _apply_safe_domain_cooldown(self, url: str) -> None:
        if not bool(getattr(settings, "BROWSER_SAFE_MODE_ENABLED", True)):
            return
        domain = self._extract_domain(url)
        if not domain:
            return
        cooldown_ms = max(0, int(getattr(settings, "BROWSER_DOMAIN_COOLDOWN_MS", 1200) or 1200))
        now = time.monotonic()
        async with self._domain_lock:
            prev = float(self._domain_last_action.get(domain, 0.0) or 0.0)
            wait_sec = max(0.0, (cooldown_ms / 1000.0) - (now - prev))
            if wait_sec > 0:
                await asyncio.sleep(wait_sec)
            self._domain_last_action[domain] = time.monotonic()

    def _challenge_keywords(self) -> list[str]:
        raw = str(
            getattr(
                settings,
                "BROWSER_CHALLENGE_KEYWORDS",
                "captcha,challenge,verify you are human,robot check,access denied,temporarily blocked,unusual traffic",
            )
            or ""
        )
        return [x.strip().lower() for x in raw.split(",") if x.strip()]

    async def _detect_challenge(self, page, url_hint: str = "") -> tuple[bool, str]:
        if not bool(getattr(settings, "BROWSER_CHALLENGE_DETECT_ENABLED", True)):
            return False, ""
        try:
            cur_url = str(getattr(page, "url", "") or url_hint or "")
            low_url = cur_url.lower()
            if any(k in low_url for k in ("captcha", "challenge", "blocked", "robot")):
                return True, f"url={cur_url}"
            body = ""
            try:
                body = (await page.inner_text("body") or "")[:4000].lower()
            except Exception:
                body = ""
            for kw in self._challenge_keywords():
                if kw and kw in body:
                    return True, f"keyword={kw}"
            return False, ""
        except Exception:
            return False, ""

    async def _goto_with_policy(self, page, url: str, timeout_ms: int = 30000):
        profile = self._runtime_profile(self._context_service)
        if bool(getattr(settings, "BROWSER_SAFE_MODE_ENABLED", True)):
            await self._apply_safe_domain_cooldown(url)
            min_d = int(getattr(settings, "BROWSER_MIN_ACTION_DELAY_MS", 180) or 180)
            max_d = int(getattr(settings, "BROWSER_MAX_ACTION_DELAY_MS", 700) or 700)
            await page.wait_for_timeout(self._random_delay_ms(min_d, max_d))
        await self._human_browser.before_navigation(page, profile=profile, url=url)

        max_attempts = max(1, int(getattr(settings, "BROWSER_NAV_RETRY_MAX", 2) or 2))
        backoff_ms = max(0, int(getattr(settings, "BROWSER_NAV_RETRY_BACKOFF_MS", 900) or 900))
        last_exc: Exception | None = None
        response = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(400)
                await self._human_browser.after_navigation(page, profile=profile, url=url)
                return response
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                transient = any(x in msg for x in ("timeout", "net::", "connection", "temporar"))
                if attempt >= max_attempts or not transient:
                    raise
                await page.wait_for_timeout(backoff_ms * attempt)
        if last_exc is not None:
            raise last_exc
        return response

    async def _capture_failure_artifacts(self, page, prefix: str = "browser") -> dict[str, str]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        shot = f"/tmp/{prefix}_{ts}.png"
        html = f"/tmp/{prefix}_{ts}.html"
        out: dict[str, str] = {}
        try:
            await page.screenshot(path=shot, full_page=True)
            out["screenshot"] = shot
        except Exception:
            pass
        try:
            content = await page.content()
            with open(html, "w", encoding="utf-8", errors="ignore") as f:
                f.write(content or "")
            out["html"] = html
        except Exception:
            pass
        return out

    def _runtime_profile(self, service: str) -> dict[str, Any]:
        return get_browser_runtime_profile(service)

    def _default_screenshot_path(self, service: str, task_type: str) -> str:
        svc = str(service or "generic").strip().lower() or "generic"
        task = str(task_type or "step").strip().lower() or "step"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"/tmp/{svc}_{task}_{ts}.png"

    async def navigate(self, url: str, service: str = "") -> TaskResult:
        page = await self._new_page(service)
        try:
            response = await self._goto_with_policy(page, url, timeout_ms=30000)
            profile = self._runtime_profile(service)
            body_text = ""
            try:
                body_text = (await page.inner_text("body") or "")[:4000]
            except Exception:
                body_text = ""
            auth_interrupt = build_auth_interrupt_output(service, url=str(getattr(page, "url", url)), body_text=body_text)
            if auth_interrupt:
                if profile.get("screenshot_first_default") and not auth_interrupt.get("screenshot"):
                    try:
                        shot = self._default_screenshot_path(service, "auth_interrupt")
                        await page.screenshot(path=shot, full_page=True)
                        auth_interrupt["screenshot"] = shot
                    except Exception:
                        pass
                return TaskResult(success=False, error="auth_interrupt", output=auth_interrupt)
            blocked, reason = await self._detect_challenge(page, url)
            if blocked and bool(getattr(settings, "BROWSER_CHALLENGE_BLOCK_MODE", True)):
                artifacts = await self._capture_failure_artifacts(page, "challenge_detected")
                return TaskResult(
                    success=False,
                    error="challenge_detected",
                    output={"url": str(getattr(page, "url", url)), "reason": reason, "needs_manual_auth": True, **artifacts},
                )
            title = await page.title()
            output = {
                "url": url,
                "title": title,
                "status": response.status if response else 0,
                "browser_runtime_profile": profile,
                "browser_skill_pack": self.get_skill_pack(),
            }
            if profile.get("screenshot_first_default"):
                try:
                    shot = self._default_screenshot_path(service, "navigate")
                    await page.screenshot(path=shot, full_page=True)
                    output["screenshot_path"] = shot
                except Exception:
                    pass
            return TaskResult(success=True, output=output)
        except Exception as e:
            artifacts = await self._capture_failure_artifacts(page, "navigate_fail")
            return TaskResult(success=False, error=str(e), output={"url": url, **artifacts})
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def screenshot(self, url: str, path: str = "", service: str = "") -> TaskResult:
        if not path:
            path = f"/tmp/vito_screenshot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        page = await self._new_page(service)
        try:
            await self._goto_with_policy(page, url, timeout_ms=30000)
            body_text = ""
            try:
                body_text = (await page.inner_text("body") or "")[:4000]
            except Exception:
                body_text = ""
            auth_interrupt = build_auth_interrupt_output(service, url=str(getattr(page, "url", url)), body_text=body_text, screenshot_path=path)
            if auth_interrupt:
                return TaskResult(success=False, error="auth_interrupt", output=auth_interrupt)
            blocked, reason = await self._detect_challenge(page, url)
            if blocked and bool(getattr(settings, "BROWSER_CHALLENGE_BLOCK_MODE", True)):
                artifacts = await self._capture_failure_artifacts(page, "challenge_detected")
                return TaskResult(
                    success=False,
                    error="challenge_detected",
                    output={"url": str(getattr(page, "url", url)), "reason": reason, "needs_manual_auth": True, **artifacts},
                )
            await page.screenshot(path=path, full_page=True)
            return TaskResult(success=True, output={"url": url, "path": path, "size_bytes": os.path.getsize(path), "browser_runtime_profile": self._runtime_profile(service)})
        except Exception as e:
            artifacts = await self._capture_failure_artifacts(page, "screenshot_fail")
            return TaskResult(success=False, error=str(e), output={"url": url, **artifacts})
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def extract_text(self, url: str, selector: str = "body", service: str = "") -> TaskResult:
        page = await self._new_page(service)
        try:
            await self._goto_with_policy(page, url, timeout_ms=30000)
            body_text = ""
            try:
                body_text = (await page.inner_text("body") or "")[:4000]
            except Exception:
                body_text = ""
            auth_interrupt = build_auth_interrupt_output(service, url=str(getattr(page, "url", url)), body_text=body_text)
            if auth_interrupt:
                return TaskResult(success=False, error="auth_interrupt", output=auth_interrupt)
            blocked, reason = await self._detect_challenge(page, url)
            if blocked and bool(getattr(settings, "BROWSER_CHALLENGE_BLOCK_MODE", True)):
                artifacts = await self._capture_failure_artifacts(page, "challenge_detected")
                return TaskResult(
                    success=False,
                    error="challenge_detected",
                    output={"url": str(getattr(page, "url", url)), "reason": reason, "needs_manual_auth": True, **artifacts},
                )
            text = await page.inner_text(selector)
            return TaskResult(
                success=True,
                output="\n".join(l.strip() for l in text.splitlines() if l.strip())[:10000],
                metadata={"browser_runtime_profile": self._runtime_profile(service)},
            )
        except Exception as e:
            artifacts = await self._capture_failure_artifacts(page, "extract_fail")
            return TaskResult(success=False, error=str(e), output={"url": url, "selector": selector, **artifacts})
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def fill_form(self, url: str, data: dict[str, str], screenshot_path: str = "", service: str = "") -> TaskResult:
        page = await self._new_page(service)
        try:
            await self._goto_with_policy(page, url, timeout_ms=30000)
            profile = self._runtime_profile(service)
            preflight = build_form_fill_preflight(data)
            if profile.get("screenshot_first_default") and not screenshot_path:
                screenshot_path = self._default_screenshot_path(service, "form_fill")
            body_text = ""
            try:
                body_text = (await page.inner_text("body") or "")[:4000]
            except Exception:
                body_text = ""
            auth_interrupt = build_auth_interrupt_output(service, url=str(getattr(page, "url", url)), body_text=body_text, screenshot_path=screenshot_path)
            if auth_interrupt:
                return TaskResult(success=False, error="auth_interrupt", output=auth_interrupt)
            blocked, reason = await self._detect_challenge(page, url)
            if blocked and bool(getattr(settings, "BROWSER_CHALLENGE_BLOCK_MODE", True)):
                artifacts = await self._capture_failure_artifacts(page, "challenge_detected")
                return TaskResult(
                    success=False,
                    error="challenge_detected",
                    output={"url": str(getattr(page, "url", url)), "reason": reason, "needs_manual_auth": True, **artifacts},
                )
            if preflight["selector_mapping_required"]:
                shot = ""
                if screenshot_path:
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        shot = screenshot_path
                    except Exception:
                        pass
                return TaskResult(
                    success=True,
                    output={
                        "fields_filled": 0,
                        "total": len(data or {}),
                        "selector_mapping_required": True,
                        "preflight": preflight,
                        "screenshot_path": shot,
                        "browser_runtime_profile": profile,
                        "browser_recovery": build_browser_recovery(service, "form_fill", "selector_mapping_required"),
                        "browser_skill_pack": self.get_skill_pack(),
                    },
                )
            filled = 0
            for sel, val in data.items():
                if not looks_like_selector(sel):
                    continue
                try:
                    await self._human_browser.type_text(page, sel, val, profile=profile)
                    filled += 1
                except Exception:
                    pass
            if filled == 0:
                shot = ""
                if screenshot_path:
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        shot = screenshot_path
                    except Exception:
                        pass
                return TaskResult(
                    success=True,
                    output={
                        "fields_filled": 0,
                        "total": len(data or {}),
                        "selector_mapping_required": True,
                        "preflight": preflight,
                        "screenshot_path": shot,
                        "browser_runtime_profile": profile,
                        "browser_recovery": build_browser_recovery(service, "form_fill", "no_matching_selectors"),
                        "browser_skill_pack": self.get_skill_pack(),
                    },
                )
            shot = ""
            if screenshot_path:
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    shot = screenshot_path
                except Exception:
                    pass
            return TaskResult(
                success=True,
                output={
                    "fields_filled": filled,
                    "total": len(data),
                    "screenshot_path": shot,
                    "browser_runtime_profile": profile,
                    "browser_skill_pack": self.get_skill_pack(),
                },
            )
        except Exception as e:
            artifacts = await self._capture_failure_artifacts(page, "form_fail")
            return TaskResult(success=False, error=str(e), output={"url": url, **artifacts})
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def upload_file(self, url: str, file_path: str, selector: str = 'input[type="file"]', screenshot_path: str = "", service: str = "") -> TaskResult:
        if not os.path.isfile(file_path):
            return TaskResult(success=False, error=f"Файл не найден: {file_path}")
        page = await self._new_page(service)
        try:
            await self._goto_with_policy(page, url, timeout_ms=30000)
            profile = self._runtime_profile(service)
            if profile.get("screenshot_first_default") and not screenshot_path:
                screenshot_path = self._default_screenshot_path(service, "upload_file")
            body_text = ""
            try:
                body_text = (await page.inner_text("body") or "")[:4000]
            except Exception:
                body_text = ""
            auth_interrupt = build_auth_interrupt_output(service, url=str(getattr(page, "url", url)), body_text=body_text, screenshot_path=screenshot_path)
            if auth_interrupt:
                return TaskResult(success=False, error="auth_interrupt", output=auth_interrupt)
            blocked, reason = await self._detect_challenge(page, url)
            if blocked and bool(getattr(settings, "BROWSER_CHALLENGE_BLOCK_MODE", True)):
                artifacts = await self._capture_failure_artifacts(page, "challenge_detected")
                return TaskResult(
                    success=False,
                    error="challenge_detected",
                    output={"url": str(getattr(page, "url", url)), "reason": reason, "needs_manual_auth": True, **artifacts},
                )
            fi = await page.query_selector(selector)
            if fi:
                await fi.set_input_files(file_path)
                shot = ""
                if screenshot_path:
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        shot = screenshot_path
                    except Exception:
                        pass
                    return TaskResult(
                        success=True,
                        output={
                            "uploaded": True,
                            "file": file_path,
                            "screenshot_path": shot,
                            "browser_runtime_profile": profile,
                            "browser_skill_pack": self.get_skill_pack(),
                        },
                    )
            artifacts = await self._capture_failure_artifacts(page, "upload_selector_missing")
            return TaskResult(success=False, error=f"Селектор не найден: {selector}", output={"url": url, **artifacts})
        except Exception as e:
            artifacts = await self._capture_failure_artifacts(page, "upload_fail")
            return TaskResult(success=False, error=str(e), output={"url": url, **artifacts})
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def register_with_email(
        self,
        url: str,
        form: dict[str, str],
        submit_selector: str,
        code_selector: str = "",
        code_submit_selector: str = "",
        from_filter: str = "",
        subject_filter: str = "",
        prefer_link: bool = False,
        timeout_sec: int = 180,
        screenshot_path: str = "",
        verify_selectors: list[str] | None = None,
        require_verify: bool = False,
        service: str = "",
    ) -> TaskResult:
        """Generic registration flow: fill form, submit, fetch email code/link, submit."""
        page = await self._new_page(service)
        try:
            await self._goto_with_policy(page, url, timeout_ms=30000)
            profile = self._runtime_profile(service)
            if profile.get("screenshot_first_default") and not screenshot_path:
                screenshot_path = self._default_screenshot_path(service, "register")
            body_text = ""
            try:
                body_text = (await page.inner_text("body") or "")[:4000]
            except Exception:
                body_text = ""
            auth_interrupt = build_auth_interrupt_output(service, url=str(getattr(page, "url", url)), body_text=body_text, screenshot_path=screenshot_path)
            if auth_interrupt:
                return TaskResult(success=False, error="auth_interrupt", output=auth_interrupt)
            blocked, reason = await self._detect_challenge(page, url)
            if blocked and bool(getattr(settings, "BROWSER_CHALLENGE_BLOCK_MODE", True)):
                artifacts = await self._capture_failure_artifacts(page, "challenge_detected")
                return TaskResult(
                    success=False,
                    error="challenge_detected",
                    output={"url": str(getattr(page, "url", url)), "reason": reason, "needs_manual_auth": True, **artifacts},
                )
            # Fill fields
            filled = 0
            missing_requirements: list[str] = []
            if not form:
                missing_requirements.append("form_fields")
            if not submit_selector:
                missing_requirements.append("submit_selector")
            if missing_requirements:
                shot = ""
                if screenshot_path:
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        shot = screenshot_path
                    except Exception:
                        pass
                return TaskResult(
                    success=True,
                    output={
                        "fields_filled": 0,
                        "registration_state": "preflight_incomplete",
                        "missing_requirements": missing_requirements,
                        "screenshot_path": shot,
                        "url": page.url,
                        "browser_runtime_profile": profile,
                        "browser_recovery": build_browser_recovery(service, "register_with_email", "preflight_incomplete"),
                        "browser_skill_pack": self.get_skill_pack(),
                    },
                )
            for sel, val in (form or {}).items():
                try:
                    await self._human_browser.type_text(page, sel, val, profile=profile)
                    filled += 1
                except Exception:
                    pass
            # Submit form
            try:
                await self._human_browser.click(page, submit_selector, profile=profile, timeout=5000)
            except Exception:
                pass

            code_val = ""
            if code_selector:
                # Fetch email code/link via account_manager
                try:
                    from agents.account_manager import AccountManager
                    mgr = AccountManager()
                    res = await mgr.fetch_email_code(
                        from_filter=from_filter,
                        subject_filter=subject_filter,
                        prefer_link=prefer_link,
                        timeout_sec=timeout_sec,
                    )
                    if res and res.success and isinstance(res.output, dict):
                        code_val = res.output.get("code") or ""
                except Exception:
                    pass
                if code_val:
                    try:
                        await page.fill(code_selector, code_val)
                        if bool(getattr(settings, "BROWSER_HUMANIZE_ENABLED", True)):
                            await page.wait_for_timeout(self._random_delay_ms(40, 140))
                    except Exception:
                        pass
                    if code_submit_selector:
                        try:
                            await self._human_browser.click(page, code_submit_selector, profile=profile, timeout=5000)
                        except Exception:
                            pass
            shot = ""
            if screenshot_path:
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    shot = screenshot_path
                except Exception:
                    pass
            ver = {"verified": False, "matched_selectors": []}
            if verify_selectors:
                for sel in verify_selectors:
                    try:
                        n = await page.locator(sel).count()
                        if n > 0:
                            ver["matched_selectors"].append(sel)
                    except Exception:
                        continue
                ver["verified"] = bool(ver["matched_selectors"])
            success = bool(filled) and (ver["verified"] if (require_verify and verify_selectors) else True)
            try:
                from modules.execution_facts import ExecutionFacts
                ExecutionFacts().record(
                    action="browser:register_with_email",
                    status="success" if success else "failed",
                    detail=f"url={url[:120]} filled={filled} verified={ver['verified']}",
                    evidence=shot or "",
                    source="browser_agent.register_with_email",
                    evidence_dict={"url": page.url, "verify": ver, "code_used": bool(code_val)},
                )
            except Exception:
                pass
            return TaskResult(
                success=success,
                output={
                    "fields_filled": filled,
                    "code_used": bool(code_val),
                        "screenshot_path": shot,
                        "url": page.url,
                        "browser_runtime_profile": profile,
                        **ver,
                    },
                )
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def solve_captcha(self, page) -> Optional[str]:
        """Detect and solve CAPTCHA on a Playwright page.

        Uses the global CaptchaSolver singleton. Returns the token if solved, None otherwise.
        Works with reCAPTCHA v2, v3, and hCaptcha.
        """
        try:
            from modules.captcha_solver import CaptchaSolver
            solver = CaptchaSolver.get_instance()
            token = await solver.solve_playwright_recaptcha(page)
            if token:
                logger.info(f"CAPTCHA solved on {page.url}", extra={"event": "captcha_solved"})
            else:
                logger.warning(f"CAPTCHA solve failed on {page.url}", extra={"event": "captcha_failed"})
            return token
        except Exception as e:
            logger.error(f"CAPTCHA solve error: {e}", extra={"event": "captcha_error"})
            return None

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        try:
            if task_type in ("browse", "navigate"):
                return await self.navigate(kwargs.get("url", ""), service=kwargs.get("service", ""))
            elif task_type == "screenshot":
                return await self.screenshot(kwargs.get("url", ""), kwargs.get("path", ""), service=kwargs.get("service", ""))
            elif task_type in ("web_scrape", "extract_text"):
                return await self.extract_text(kwargs.get("url", ""), kwargs.get("selector", "body"), service=kwargs.get("service", ""))
            elif task_type == "form_fill":
                return await self.fill_form(kwargs.get("url", ""), kwargs.get("data", {}), kwargs.get("screenshot_path", ""), service=kwargs.get("service", ""))
            elif task_type == "upload_file":
                return await self.upload_file(kwargs.get("url", ""), kwargs.get("file_path", ""), kwargs.get("selector", 'input[type="file"]'), kwargs.get("screenshot_path", ""), service=kwargs.get("service", ""))
            elif task_type == "register_with_email":
                return await self.register_with_email(
                    url=kwargs.get("url", ""),
                    form=kwargs.get("form", {}) or {},
                    submit_selector=kwargs.get("submit_selector", ""),
                    code_selector=kwargs.get("code_selector", ""),
                    code_submit_selector=kwargs.get("code_submit_selector", ""),
                    from_filter=kwargs.get("from_filter", ""),
                    subject_filter=kwargs.get("subject_filter", ""),
                    prefer_link=bool(kwargs.get("prefer_link", False)),
                    timeout_sec=int(kwargs.get("timeout_sec", 180)),
                    screenshot_path=kwargs.get("screenshot_path", ""),
                    verify_selectors=kwargs.get("verify_selectors", []) or [],
                    require_verify=bool(kwargs.get("require_verify", False)),
                    service=kwargs.get("service", ""),
                )
            elif task_type == "solve_captcha":
                page = kwargs.get("page")
                if not page:
                    return TaskResult(success=False, error="No page provided for solve_captcha")
                token = await self.solve_captcha(page)
                return TaskResult(success=bool(token), output=token)
            return TaskResult(success=False, error=f"Неизвестный task_type: {task_type}")
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE
