"""BrowserAgent — Agent 21: headless-браузер на Playwright.

Возможности: навигация, скриншоты, извлечение текста, формы, загрузка файлов.
Singleton: один инстанс Chromium на весь жизненный цикл.

OOM Protection:
- Singleton pattern: max 1 browser instance
- --single-process + --disable-dev-shm-usage Chrome flags
- Watchdog: kills orphan headless_shell processes (max 2 allowed)
- Memory limit: systemd MemoryMax=2G (RLIMIT_AS breaks V8/Node)
- Guaranteed cleanup in finally blocks
"""

import asyncio
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.resource_guard import resource_guard

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


class BrowserAgent(BaseAgent):
    _instance: Optional["BrowserAgent"] = None
    _browser = None
    _playwright_inst = None
    _lock: Optional[asyncio.Lock] = None

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
        self._page = None
        if BrowserAgent._lock is None:
            BrowserAgent._lock = asyncio.Lock()

    @property
    def capabilities(self) -> list[str]:
        return ["browse", "web_scrape", "form_fill", "register_with_email"]

    async def start(self) -> None:
        await super().start()
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

            if BrowserAgent._playwright_inst is None:
                # Set memory limit before launching browser
                _set_memory_limit()

                BrowserAgent._playwright_inst = await async_playwright().start()
                BrowserAgent._browser = await BrowserAgent._playwright_inst.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--single-process",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--js-flags=--max-old-space-size=256",
                    ],
                )
                self._context = await BrowserAgent._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                )
                logger.info("Playwright Chromium запущен", extra={"event": "browser_started"})
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

    async def _ensure_browser(self) -> None:
        if BrowserAgent._browser is None or self._context is None:
            await self.start()

    async def _new_page(self):
        await self._ensure_browser()
        return await self._context.new_page()

    async def navigate(self, url: str) -> TaskResult:
        page = await self._new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = await page.title()
            return TaskResult(success=True, output={"url": url, "title": title, "status": response.status if response else 0})
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def screenshot(self, url: str, path: str = "") -> TaskResult:
        if not path:
            path = f"/tmp/vito_screenshot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.screenshot(path=path, full_page=True)
            return TaskResult(success=True, output={"url": url, "path": path, "size_bytes": os.path.getsize(path)})
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def extract_text(self, url: str, selector: str = "body") -> TaskResult:
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            text = await page.inner_text(selector)
            return TaskResult(success=True, output="\n".join(l.strip() for l in text.splitlines() if l.strip())[:10000])
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def fill_form(self, url: str, data: dict[str, str], screenshot_path: str = "") -> TaskResult:
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            filled = 0
            for sel, val in data.items():
                try:
                    await page.fill(sel, val)
                    filled += 1
                except Exception:
                    pass
            shot = ""
            if screenshot_path:
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    shot = screenshot_path
                except Exception:
                    pass
            return TaskResult(success=True, output={"fields_filled": filled, "total": len(data), "screenshot_path": shot})
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def upload_file(self, url: str, file_path: str, selector: str = 'input[type="file"]', screenshot_path: str = "") -> TaskResult:
        if not os.path.isfile(file_path):
            return TaskResult(success=False, error=f"Файл не найден: {file_path}")
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
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
                return TaskResult(success=True, output={"uploaded": True, "file": file_path, "screenshot_path": shot})
            return TaskResult(success=False, error=f"Селектор не найден: {selector}")
        except Exception as e:
            return TaskResult(success=False, error=str(e))
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
    ) -> TaskResult:
        """Generic registration flow: fill form, submit, fetch email code/link, submit."""
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Fill fields
            filled = 0
            for sel, val in (form or {}).items():
                try:
                    await page.fill(sel, val)
                    filled += 1
                except Exception:
                    pass
            # Submit form
            try:
                await page.click(submit_selector, timeout=5000)
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
                    except Exception:
                        pass
                    if code_submit_selector:
                        try:
                            await page.click(code_submit_selector, timeout=5000)
                        except Exception:
                            pass
            shot = ""
            if screenshot_path:
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    shot = screenshot_path
                except Exception:
                    pass
            return TaskResult(
                success=bool(filled),
                output={
                    "fields_filled": filled,
                    "code_used": bool(code_val),
                    "screenshot_path": shot,
                    "url": page.url,
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
                return await self.navigate(kwargs.get("url", ""))
            elif task_type == "screenshot":
                return await self.screenshot(kwargs.get("url", ""), kwargs.get("path", ""))
            elif task_type in ("web_scrape", "extract_text"):
                return await self.extract_text(kwargs.get("url", ""), kwargs.get("selector", "body"))
            elif task_type == "form_fill":
                return await self.fill_form(kwargs.get("url", ""), kwargs.get("data", {}), kwargs.get("screenshot_path", ""))
            elif task_type == "upload_file":
                return await self.upload_file(kwargs.get("url", ""), kwargs.get("file_path", ""), kwargs.get("selector", 'input[type="file"]'), kwargs.get("screenshot_path", ""))
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
