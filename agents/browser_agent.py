"""BrowserAgent — Agent 21: headless-браузер на Playwright.

Возможности: навигация, скриншоты, извлечение текста, формы, загрузка файлов.
Singleton: один инстанс Chromium на весь жизненный цикл.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger

logger = get_logger("browser_agent", agent="browser_agent")


class BrowserAgent(BaseAgent):
    _instance: Optional["BrowserAgent"] = None
    _browser = None
    _playwright_inst = None

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

    @property
    def capabilities(self) -> list[str]:
        return ["browse", "web_scrape", "form_fill"]

    async def start(self) -> None:
        await super().start()
        try:
            from playwright.async_api import async_playwright
            if BrowserAgent._playwright_inst is None:
                BrowserAgent._playwright_inst = await async_playwright().start()
                BrowserAgent._browser = await BrowserAgent._playwright_inst.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                self._context = await BrowserAgent._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                )
                logger.info("Playwright Chromium запущен", extra={"event": "browser_started"})
        except Exception as e:
            self._status = AgentStatus.ERROR
            logger.error(f"Ошибка запуска Playwright: {e}", extra={"event": "browser_start_failed"}, exc_info=True)

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
        finally:
            BrowserAgent._instance = None
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
            await page.close()

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
            await page.close()

    async def extract_text(self, url: str, selector: str = "body") -> TaskResult:
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            text = await page.inner_text(selector)
            return TaskResult(success=True, output="\n".join(l.strip() for l in text.splitlines() if l.strip())[:10000])
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            await page.close()

    async def fill_form(self, url: str, data: dict[str, str]) -> TaskResult:
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
            return TaskResult(success=True, output={"fields_filled": filled, "total": len(data)})
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            await page.close()

    async def upload_file(self, url: str, file_path: str, selector: str = 'input[type="file"]') -> TaskResult:
        if not os.path.isfile(file_path):
            return TaskResult(success=False, error=f"Файл не найден: {file_path}")
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            fi = await page.query_selector(selector)
            if fi:
                await fi.set_input_files(file_path)
                return TaskResult(success=True, output={"uploaded": True, "file": file_path})
            return TaskResult(success=False, error=f"Селектор не найден: {selector}")
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            await page.close()

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
                return await self.fill_form(kwargs.get("url", ""), kwargs.get("data", {}))
            elif task_type == "upload_file":
                return await self.upload_file(kwargs.get("url", ""), kwargs.get("file_path", ""))
            return TaskResult(success=False, error=f"Неизвестный task_type: {task_type}")
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE
