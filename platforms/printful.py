"""PrintfulPlatform — интеграция с Printful REST API (print-on-demand)."""

import json
import os
from typing import Any
from pathlib import Path

import aiohttp

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("printful", agent="printful")
API_BASE = "https://api.printful.com"


class PrintfulPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="printful", **kwargs)
        self._api_key = getattr(settings, "PRINTFUL_API_KEY", "")
        self._store_id = str(getattr(settings, "PRINTFUL_STORE_ID", "") or "")
        self._mode: str = str(getattr(settings, "PRINTFUL_MODE", "api") or "api").strip().lower()
        self._storage_state_path = Path(
            str(getattr(settings, "PRINTFUL_STORAGE_STATE_FILE", "runtime/printful_storage_state.json") or "runtime/printful_storage_state.json")
        )
        if not self._storage_state_path.is_absolute():
            self._storage_state_path = PROJECT_ROOT / self._storage_state_path
        self._store_type: str = ""
        self._session: aiohttp.ClientSession | None = None

    async def _publish_via_browser(self, content: dict) -> dict:
        if not self._storage_state_path.exists():
            return {
                "platform": "printful",
                "status": "needs_browser_login",
                "error": "Printful browser session required.",
                "storage_state": str(self._storage_state_path),
            }
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {"platform": "printful", "status": "error", "error": "playwright_not_installed"}

        shot = str(PROJECT_ROOT / "runtime" / "printful_browser_publish.png")
        html_dump = str(PROJECT_ROOT / "runtime" / "printful_browser_publish.html")
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
                )
                page = await context.new_page()
                await page.goto("https://www.printful.com/dashboard/store", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(3500)
                cur = (page.url or "").lower()
                if any(x in cur for x in ("/login", "/signin", "captcha", "challenge")):
                    return {
                        "platform": "printful",
                        "status": "needs_browser_login",
                        "error": "Stored Printful session expired.",
                        "storage_state": str(self._storage_state_path),
                        "url": page.url,
                    }

                # Try to open product templates page for connected store.
                templates_href = ""
                try:
                    templates_href = await page.evaluate(
                        """() => {
                            const links = Array.from(document.querySelectorAll('a[href]'));
                            const x = links.find(a => (a.getAttribute('href') || '').includes('/dashboard/product-templates/published/'));
                            return x ? (x.getAttribute('href') || '') : '';
                        }"""
                    ) or ""
                except Exception:
                    templates_href = ""
                if templates_href:
                    if templates_href.startswith("/"):
                        templates_href = f"https://www.printful.com{templates_href}"
                    await page.goto(templates_href, wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(2500)

                target_title = str((content or {}).get("sync_product", {}).get("name") or "").strip()
                created = False
                action_url = ""

                # Best-effort click on "Create product".
                for sel in (
                    'a:has-text("Create product")',
                    'button:has-text("Create product")',
                    'a[href*="/dashboard/custom-products"]',
                ):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.click(timeout=2500)
                            await page.wait_for_timeout(2500)
                            action_url = page.url
                            if "/dashboard/custom/" in (page.url or "").lower() or "/dashboard/custom-products" in (page.url or "").lower():
                                created = True
                                break
                    except Exception:
                        continue

                # Capture any stable "my products" url as evidence anchor.
                product_url = ""
                try:
                    product_url = await page.evaluate(
                        """() => {
                            const links = Array.from(document.querySelectorAll('a[href]'));
                            const x = links.find(a => (a.getAttribute('href') || '').includes('/dashboard/product-templates/published/'));
                            return x ? (x.getAttribute('href') || '') : '';
                        }"""
                    ) or ""
                except Exception:
                    product_url = ""
                if product_url and product_url.startswith("/"):
                    product_url = f"https://www.printful.com{product_url}"

                # Optional title typing if name field is visible after create click.
                if created and target_title:
                    try:
                        for sel in ('input[name="name"]', 'input[placeholder*="name" i]', 'input[aria-label*="name" i]'):
                            loc = page.locator(sel)
                            if await loc.count():
                                await loc.first.fill(target_title[:120])
                                break
                    except Exception:
                        pass

                try:
                    Path(html_dump).write_text(await page.content(), encoding="utf-8")
                except Exception:
                    pass
                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass

                result_status = "created" if created else "prepared"
                result_url = product_url or action_url or page.url
                result = {
                    "platform": "printful",
                    "status": result_status,
                    "url": result_url,
                    "mode": "browser_only",
                    "screenshot_path": shot,
                    "html_path": html_dump,
                    "store_type": self._store_type or "",
                }
                try:
                    ExecutionFacts().record(
                        action="platform:publish",
                        status=result_status,
                        detail=f"printful browser {result_status}",
                        evidence=result_url,
                        source="printful.publish.browser",
                        evidence_dict={"platform": "printful", "status": result_status, "url": result_url},
                    )
                except Exception:
                    pass
                return result
        except Exception as e:
            return {"platform": "printful", "status": "error", "error": str(e)}
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

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers())
        return self._session

    async def authenticate(self) -> bool:
        """GET /stores — проверка токена и доступных stores."""
        if self._mode in {"browser", "browser_only"}:
            if not self._storage_state_path.exists():
                self._authenticated = False
                return False
            try:
                data = json.loads(self._storage_state_path.read_text(encoding="utf-8"))
                cookies = data.get("cookies") if isinstance(data, dict) else None
                self._authenticated = bool(isinstance(cookies, list) and cookies)
                return self._authenticated
            except Exception:
                self._authenticated = False
                return False
        if not self._api_key:
            self._authenticated = False
            return False
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/stores") as resp:
                if resp.status != 200:
                    self._authenticated = False
                    return False
                data = await resp.json()
                stores = list((data or {}).get("result", []) or [])
                if not self._store_id and stores:
                    first = stores[0] if isinstance(stores[0], dict) else {}
                    sid = first.get("id")
                    if sid is not None:
                        self._store_id = str(sid)
                for st in stores:
                    if not isinstance(st, dict):
                        continue
                    if str(st.get("id", "")) == str(self._store_id):
                        self._store_type = str(st.get("type", "") or "")
                        break
                self._authenticated = True
                logger.info(
                    "Printful авторизация успешна",
                    extra={"event": "printful_auth_ok", "context": {"stores": len(stores), "store_id": self._store_id, "store_type": self._store_type}},
                )
                return True
        except Exception as e:
            logger.error(f"Printful auth error: {e}", extra={"event": "printful_auth_error"})
            self._authenticated = False
            return False

    async def _sync_products_probe(self) -> dict[str, Any]:
        if not self._store_id:
            return {"ok": False, "error": "no_store_id"}
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/sync/products", params={"store_id": self._store_id}) as resp:
                data = await resp.json()
                if resp.status != 200:
                    return {"ok": False, "status": resp.status, "error": str((data or {}).get("error", {}))}
                result = (data or {}).get("result", []) if isinstance(data, dict) else []
                return {"ok": True, "count": len(result) if isinstance(result, list) else 0}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _create_via_sync_api(self, content: dict) -> dict:
        """Fallback for non-API stores (Etsy/Shopify connected): try Sync API create path."""
        if not self._store_id:
            return {"platform": "printful", "status": "error", "error": "no_store_connected"}
        sync_product = dict((content or {}).get("sync_product") or {})
        if not sync_product.get("name"):
            sync_product["name"] = "VITO Sync Product"
        payload = {
            "sync_product": sync_product,
            "sync_variants": list((content or {}).get("sync_variants") or []),
        }
        try:
            session = await self._get_session()
            async with session.post(f"{API_BASE}/store/products", params={"store_id": self._store_id}, json=payload) as resp:
                data = await resp.json()
                code = int((data or {}).get("code", 0) or 0) if isinstance(data, dict) else 0
                if resp.status >= 400 or code >= 400:
                    return {"platform": "printful", "status": "error", "error": str(data)[:500], "data": data}
                result = (data or {}).get("result", {}) if isinstance(data, dict) else {}
                pid = str(result.get("id") or "")
                url = f"https://www.printful.com/dashboard/store/products/{pid}" if pid else ""
                return {"platform": "printful", "status": "created", "id": pid, "url": url, "data": data}
        except Exception as e:
            return {"platform": "printful", "status": "error", "error": str(e)}

    async def publish(self, content: dict) -> dict:
        """POST /store/products — создание продукта."""
        if self._mode in {"browser", "browser_only"}:
            return await self._publish_via_browser(content or {})
        if content.get("dry_run"):
            name = (content.get("sync_product", {}) or {}).get("name", "printful_dryrun")
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"printful dry_run name={str(name)[:80]}",
                    evidence="dryrun:printful",
                    source="printful.publish",
                    evidence_dict={"platform": "printful", "dry_run": True, "name": name},
                )
            except Exception:
                pass
            return {
                "platform": "printful",
                "status": "prepared",
                "dry_run": True,
                "name": name,
            }

        if not self._authenticated:
            return {"platform": "printful", "status": "not_authenticated"}
        if not self._store_id:
            return {"platform": "printful", "status": "error", "error": "no_store_connected"}
        if self._store_type and self._store_type != "api":
            probe = await self._sync_products_probe()
            # Attempt Sync API path first; only fallback to browser flow if denied.
            via_sync = await self._create_via_sync_api(content)
            if str(via_sync.get("status") or "") == "created":
                return via_sync
            browser_out = await self._publish_via_browser(content or {})
            if str(browser_out.get("status") or "") in {"created", "prepared"}:
                browser_out["sync_probe"] = probe
                browser_out["sync_attempt"] = via_sync
                return browser_out
            return {
                "platform": "printful",
                "status": "needs_browser_flow",
                "error": (
                    f"Store type '{self._store_type}' does not support create via current API path. "
                    "Use browser flow in Printful dashboard (linked Etsy store)."
                ),
                "store_type": self._store_type,
                "sync_probe": probe,
                "sync_attempt": via_sync,
                "browser_attempt": browser_out,
            }
        try:
            session = await self._get_session()
            async with session.post(f"{API_BASE}/store/products", params={"store_id": self._store_id}, json=content) as resp:
                data = await resp.json()
                code = int((data or {}).get("code", 0) or 0) if isinstance(data, dict) else 0
                err = (data or {}).get("error", {}) if isinstance(data, dict) else {}
                err_msg = str(err.get("message") or (data or {}).get("result") or "").strip() if isinstance(data, dict) else ""
                if resp.status >= 400 or code >= 400 or err_msg:
                    # Common real-world case: store is Etsy/Shopify-connected and /store/products API is not allowed.
                    restricted = "manual order / api platform" in err_msg.lower()
                    status = "needs_browser_flow" if restricted else "error"
                    result = {
                        "platform": "printful",
                        "status": status,
                        "error": err_msg or f"HTTP {resp.status}",
                        "data": data,
                    }
                    logger.warning(
                        f"Printful publish rejected: {result['error']}",
                        extra={"event": "printful_publish_rejected", "context": {"status": status, "store_id": self._store_id}},
                    )
                    return result
                logger.info(
                    f"Printful продукт создан: {content.get('sync_product', {}).get('name', 'unknown')}",
                    extra={"event": "printful_publish"},
                )
                try:
                    product = (data or {}).get("result", {}) if isinstance(data, dict) else {}
                    pid = product.get("id", "")
                    evidence = f"https://www.printful.com/dashboard/store/products/{pid}" if pid else ""
                    ExecutionFacts().record(
                        action="platform:publish",
                        status="created",
                        detail=f"printful product_id={pid}",
                        evidence=evidence,
                        source="printful.publish",
                        evidence_dict={"platform": "printful", "product_id": pid, "url": evidence},
                    )
                except Exception:
                    pass
                return {"platform": "printful", "status": "created", "data": data}
        except Exception as e:
            logger.error(f"Printful publish error: {e}", extra={"event": "printful_publish_error"})
            return {"platform": "printful", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """GET /orders — аналитика заказов."""
        if not self._authenticated:
            return {"platform": "printful", "orders": 0, "revenue": 0.0}
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/orders") as resp:
                data = await resp.json()
                orders = data.get("result", [])
                revenue = sum(
                    float(o.get("retail_costs", {}).get("total", 0)) for o in orders
                )
                return {"platform": "printful", "orders": len(orders), "revenue": revenue}
        except Exception as e:
            logger.error(f"Printful analytics error: {e}", extra={"event": "printful_analytics_error"})
            return {"platform": "printful", "orders": 0, "revenue": 0.0, "error": str(e)}

    async def get_products(self) -> list[dict]:
        """GET /store/products — список продуктов."""
        if not self._authenticated:
            return []
        if not self._store_id:
            return []
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/store/products", params={"store_id": self._store_id}) as resp:
                data = await resp.json()
                return data.get("result", [])
        except Exception as e:
            logger.error(f"Printful products error: {e}", extra={"event": "printful_products_error"})
            return []

    async def create_mockup(self, product_id: int, files: list[dict]) -> dict:
        """POST /mockup-generator/create-task — создание мокапа."""
        if not self._authenticated:
            return {"status": "not_authenticated"}
        try:
            session = await self._get_session()
            payload = {"variant_ids": [product_id], "files": files}
            async with session.post(f"{API_BASE}/mockup-generator/create-task/{product_id}", json=payload) as resp:
                return await resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def health_check(self) -> bool:
        return bool(self._api_key)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
