"""PrintfulPlatform — интеграция с Printful REST API (print-on-demand)."""

import json
import os
from typing import Any
from pathlib import Path

import aiohttp

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from modules.platform_knowledge import record_platform_lesson
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
                page_body = ""
                try:
                    page_body = ((await page.locator("body").inner_text()) or "").lower()
                except Exception:
                    page_body = ""
                if ("/login" in cur or "/signin" in cur) or (
                    ("sign in" in page_body or "log in" in page_body)
                    and "cancel membership" not in page_body
                    and "new order" not in page_body
                ):
                    return {
                        "platform": "printful",
                        "status": "needs_browser_login",
                        "error": "Stored Printful session expired.",
                        "storage_state": str(self._storage_state_path),
                        "url": page.url,
                    }

                target_title = str((content or {}).get("sync_product", {}).get("name") or "Working Printful Product").strip()
                target_description = str((content or {}).get("sync_product", {}).get("description") or "").strip()
                target_tags = [str(x).strip() for x in ((content or {}).get("sync_product", {}) or {}).get("tags", []) if str(x).strip()]
                product_route = str((content or {}).get("product_url") or "").strip() or (
                    "https://www.printful.com/dashboard/custom/stationery/notebooks/"
                    "hardcover-bound-notebook-journalbook"
                )
                image_path = (
                    str((content or {}).get("image_path") or "").strip()
                    or str((content or {}).get("cover_path") or "").strip()
                )
                action_url = ""
                template_id = ""
                my_products_url = ""
                etsy_edit_url = ""
                created = False

                async def _abs(href: str) -> str:
                    if href.startswith("/"):
                        return f"https://www.printful.com{href}"
                    return href

                async def _click_first(selectors: tuple[str, ...], *, timeout: int = 4000) -> bool:
                    for sel in selectors:
                        try:
                            loc = page.locator(sel)
                            if await loc.count():
                                await loc.first.click(timeout=timeout)
                                return True
                        except Exception:
                            continue
                    return False

                async def _continue_publish_step() -> bool:
                    for sel in (
                        "button:has-text('Continue')",
                        "button:has-text('Next')",
                        "[data-testid='publish-modal-button-next']",
                    ):
                        try:
                            loc = page.locator(sel)
                            if await loc.count():
                                btn = loc.last
                                if await btn.is_enabled():
                                    await btn.click(timeout=3000)
                                    await page.wait_for_timeout(1500)
                                    return True
                        except Exception:
                            continue
                    return False

                async def _resolve_my_products_url() -> str:
                    try:
                        href = await page.evaluate(
                            """() => {
                                const links = Array.from(document.querySelectorAll('a[href]'));
                                const x = links.find(a => (a.getAttribute('href') || '').includes('/dashboard/product-templates/published/'));
                                return x ? (x.getAttribute('href') || '') : '';
                            }"""
                        ) or ""
                        return await _abs(href) if href else ""
                    except Exception:
                        return ""

                async def _find_synced_product(my_url: str, desired_title: str) -> dict[str, str]:
                    out = {"my_products_url": my_url or "", "etsy_edit_url": "", "product_title": "", "edit_url": ""}
                    if not my_url:
                        return out
                    try:
                        await page.goto(my_url, wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(3500)
                        found = await page.evaluate(
                            """(titleNeedle) => {
                                const rows = Array.from(document.querySelectorAll('a[href], tr, div'));
                                const needle = String(titleNeedle || '').trim().toLowerCase();
                                const links = Array.from(document.querySelectorAll('a[href]'));
                                let etsyEdit = '';
                                let editUrl = '';
                                let productTitle = '';
                                for (const a of links) {
                                    const txt = (a.textContent || '').trim();
                                    const href = a.href || '';
                                    if (/etsy\\.com\\/your\\/shops\\/.+\\/tools\\/listings\\//i.test(href)) {
                                        etsyEdit = href;
                                        const row = a.closest('tr, li, div');
                                        if (row) {
                                            const rowTxt = (row.textContent || '').trim();
                                            if (needle && rowTxt.toLowerCase().includes(needle)) {
                                                productTitle = txt || rowTxt.split('\\n')[0] || '';
                                                const editA = Array.from(row.querySelectorAll('a[href]')).find(x => /\\/dashboard\\/product-templates\\/published\\//i.test(x.href || ''));
                                                if (editA) editUrl = editA.href || '';
                                                return { etsy_edit_url: etsyEdit, edit_url: editUrl, product_title: productTitle };
                                            }
                                        }
                                    }
                                }
                                for (const row of rows) {
                                    const rowTxt = (row.textContent || '').trim();
                                    if (!needle || !rowTxt.toLowerCase().includes(needle)) continue;
                                    const anchors = Array.from(row.querySelectorAll?.('a[href]') || []);
                                    const etsy = anchors.find(a => /etsy\\.com\\/your\\/shops\\/.+\\/tools\\/listings\\//i.test(a.href || ''));
                                    const edit = anchors.find(a => /\\/dashboard\\/product-templates\\/published\\//i.test(a.href || ''));
                                    return {
                                        etsy_edit_url: etsy ? (etsy.href || '') : '',
                                        edit_url: edit ? (edit.href || '') : '',
                                        product_title: rowTxt.split('\\n')[0] || '',
                                    };
                                }
                                return { etsy_edit_url: etsyEdit, edit_url: editUrl, product_title: productTitle };
                            }""",
                            desired_title,
                        )
                        if isinstance(found, dict):
                            out.update({k: str(v or "") for k, v in found.items()})
                    except Exception:
                        return out
                    return out

                existing_linked = await _find_synced_product(await _resolve_my_products_url(), target_title)
                if existing_linked.get("etsy_edit_url"):
                    result = {
                        "platform": "printful",
                        "status": "published",
                        "url": existing_linked.get("my_products_url") or "",
                        "mode": "browser_only",
                        "screenshot_path": shot,
                        "html_path": html_dump,
                        "store_type": self._store_type or "",
                        "title": target_title[:200],
                        "template_id": "",
                        "etsy_edit_url": existing_linked.get("etsy_edit_url") or "",
                    }
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"printful synced existing title={target_title[:80]}",
                            evidence=existing_linked.get("etsy_edit_url") or existing_linked.get("my_products_url") or "",
                            source="printful.publish.browser",
                            evidence_dict=result,
                        )
                        record_platform_lesson(
                            "printful",
                            status="published",
                            summary="Existing synced Printful product reused by title.",
                            details="My Products already contained linked Etsy item; browser adapter reused it instead of creating duplicates.",
                            url=existing_linked.get("etsy_edit_url") or existing_linked.get("my_products_url") or "",
                            lessons=[
                                "Перед созданием нового Printful товара проверяй My Products по title.",
                                "Если найден linked Etsy item с Edit in Etsy, считай связку подтвержденной и не плодить дубликаты.",
                            ],
                            anti_patterns=[
                                "Не пытайся создавать новый linked product, если synced item уже существует для той же задачи.",
                            ],
                            evidence=result,
                            source="printful.publish.browser",
                        )
                    except Exception:
                        pass
                    return result

                # Open exact product route instead of catalog shells.
                await page.goto(product_route, wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(3000)
                action_url = page.url or product_route

                # Start product designer.
                await _click_first((
                    "button:has-text('Start designing')",
                    "a:has-text('Start designing')",
                ))
                await page.wait_for_timeout(4000)

                # Upload artwork.
                if image_path and os.path.isfile(image_path):
                    try:
                        file_inputs = page.locator("input[type='file']")
                        if await file_inputs.count():
                            await file_inputs.first.set_input_files(image_path, timeout=7000)
                            await page.wait_for_timeout(3500)
                    except Exception:
                        pass

                # Apply uploaded design to product from file library card.
                if image_path:
                    image_name = Path(image_path).name
                    try:
                        applied = await page.evaluate(
                            """(fileName) => {
                                const cards = Array.from(document.querySelectorAll('button, a, div'));
                                for (const node of cards) {
                                    const text = (node.textContent || '').trim();
                                    if (!text || !text.includes(fileName)) continue;
                                    let root = node;
                                    for (let i = 0; i < 4 && root; i++, root = root.parentElement) {
                                        const btns = root ? Array.from(root.querySelectorAll('button')) : [];
                                        const applyBtn = btns.find(b => /apply/i.test((b.textContent || '').trim()));
                                        if (applyBtn) {
                                            applyBtn.click();
                                            return true;
                                        }
                                    }
                                }
                                const fallback = Array.from(document.querySelectorAll('button')).find(
                                    b => /apply/i.test((b.textContent || '').trim())
                                );
                                if (fallback) {
                                    fallback.click();
                                    return true;
                                }
                                return false;
                            }""",
                            image_name,
                        )
                        if applied:
                            await page.wait_for_timeout(2500)
                    except Exception:
                        pass

                # Save template and capture template id.
                await _click_first(("button:has-text('Save template')",), timeout=5000)
                await page.wait_for_timeout(5000)
                mt = page.url or ""
                mm = None
                try:
                    import re as _re
                    mm = _re.search(r"/dashboard/product-templates/(\d+)", mt)
                except Exception:
                    mm = None
                if mm:
                    template_id = mm.group(1)
                    created = True

                # Open publish wizard from template page.
                await _click_first(("button:has-text('Publish')", "a:has-text('Publish')"), timeout=5000)
                await page.wait_for_timeout(2500)
                await _continue_publish_step()  # Mockups
                await _continue_publish_step()  # Pricing

                # Details step.
                try:
                    title_input = page.locator("#product-push-title-input")
                    if await title_input.count():
                        await title_input.first.fill(target_title[:120])
                    desc_input = page.locator("#product-push-description-input")
                    if await desc_input.count():
                        await desc_input.first.fill(target_description[:999])
                    if target_tags:
                        tag_input = page.locator("#product-push-tags-input-field_tag")
                        if await tag_input.count():
                            await tag_input.first.fill(", ".join(target_tags[:13]))
                            await page.wait_for_timeout(500)
                except Exception:
                    pass

                # Final publish to connected Etsy store.
                await _click_first(
                    (
                        "button[data-testid='publish-modal-button-next']",
                        "button:has-text('Publish')",
                        "a:has-text('Publish')",
                    ),
                    timeout=5000,
                )
                await page.wait_for_timeout(8000)

                # Post-publish verification on My Products page.
                my_products_url = await _resolve_my_products_url()
                linked = await _find_synced_product(my_products_url, target_title)
                etsy_edit_url = linked.get("etsy_edit_url") or ""

                if etsy_edit_url:
                    result_status = "published"
                    result_url = my_products_url or page.url
                else:
                    result_status = "created" if created else "prepared"
                    result_url = my_products_url or action_url or page.url

                try:
                    Path(html_dump).write_text(await page.content(), encoding="utf-8")
                except Exception:
                    pass
                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass

                page_title = ""
                try:
                    page_title = (await page.title()) or ""
                except Exception:
                    page_title = ""
                page_body = ""
                try:
                    page_body = (await page.locator("body").inner_text())[:4000]
                except Exception:
                    page_body = ""
                result = {
                    "platform": "printful",
                    "status": result_status,
                    "url": result_url,
                    "mode": "browser_only",
                    "screenshot_path": shot,
                    "html_path": html_dump,
                    "store_type": self._store_type or "",
                    "title": page_title[:200],
                    "template_id": template_id,
                    "etsy_edit_url": etsy_edit_url,
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
                try:
                    record_platform_lesson(
                        "printful",
                        status=result_status,
                        summary=f"Browser publish finished with status={result_status}.",
                        details=f"title={target_title[:120]} template_id={template_id or 'n/a'}",
                        url=etsy_edit_url or result_url,
                        lessons=[
                            "Подтверждай linked Etsy success через My Products -> Edit in Etsy.",
                            "Для Printful->Etsy browser flow реальным успехом считается synced product с Etsy edit URL.",
                        ] if result_status == "published" else [
                            "Если linked Etsy URL не найден, это еще не закрытый publish flow.",
                        ],
                        anti_patterns=[
                            "Не считай publish успешным только по открытому wizard без synced product evidence.",
                        ] if result_status != "published" else [],
                        evidence=result,
                        source="printful.publish.browser",
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

    async def _get_sync_products(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        if not self._store_id:
            return {"ok": False, "error": "no_store_id", "items": []}
        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/sync/products",
                params={"store_id": self._store_id, "limit": limit, "offset": offset},
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    return {"ok": False, "status": resp.status, "error": str((data or {}).get("error", {})), "items": []}
                items = (data or {}).get("result", []) if isinstance(data, dict) else []
                return {"ok": True, "items": items if isinstance(items, list) else [], "data": data}
        except Exception as e:
            return {"ok": False, "error": str(e), "items": []}

    def _pick_existing_sync_product(self, content: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not items:
            return None
        desired_name = str(((content or {}).get("sync_product") or {}).get("name") or "").strip().lower()
        external_id = str(((content or {}).get("sync_product") or {}).get("external_id") or "").strip()
        for item in items:
            if not isinstance(item, dict):
                continue
            sync_product = item.get("sync_product") if isinstance(item.get("sync_product"), dict) else {}
            if external_id and str(sync_product.get("external_id") or "").strip() == external_id:
                return item
            if desired_name and str(sync_product.get("name") or "").strip().lower() == desired_name:
                return item
        return items[0]

    async def _create_via_sync_api(self, content: dict) -> dict:
        """Fallback for non-API stores (Etsy/Shopify connected): try Sync API create path."""
        if not self._store_id:
            return {"platform": "printful", "status": "error", "error": "no_store_connected"}
        sync_product = dict((content or {}).get("sync_product") or {})
        if not sync_product.get("name"):
            sync_product["name"] = "Working Sync Product"
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
            sync_listing = await self._get_sync_products(limit=50, offset=0)
            sync_items = list(sync_listing.get("items") or [])
            if not sync_items:
                result = {
                    "platform": "printful",
                    "status": "needs_source_listing",
                    "error": (
                        f"Printful store type '{self._store_type}' does not allow creating a brand new product directly. "
                        "Create the source listing on Etsy first, then sync/update it from Printful."
                    ),
                    "store_type": self._store_type,
                    "store_id": self._store_id,
                    "sync_probe": probe,
                }
                return result
            selected_sync = self._pick_existing_sync_product(content, sync_items)
            if selected_sync:
                sync_product = selected_sync.get("sync_product") if isinstance(selected_sync.get("sync_product"), dict) else {}
                sync_product_id = str(sync_product.get("id") or "")
                sync_product_name = str(sync_product.get("name") or "")
                sync_product_url = (
                    f"https://www.printful.com/dashboard/store/products/{sync_product_id}"
                    if sync_product_id
                    else "https://www.printful.com/dashboard/store"
                )
                return {
                    "platform": "printful",
                    "status": "needs_sync_update_flow",
                    "error": (
                        "Connected Etsy store already has synced products. "
                        "Use the sync-update/editor flow instead of trying to create a brand new product from scratch."
                    ),
                    "store_type": self._store_type,
                    "store_id": self._store_id,
                    "sync_probe": probe,
                    "sync_product_id": sync_product_id,
                    "sync_product_name": sync_product_name,
                    "url": sync_product_url,
                }
            # Attempt Sync API path first; only fallback to browser flow if denied.
            via_sync = await self._create_via_sync_api(content)
            if str(via_sync.get("status") or "") == "created":
                return via_sync
            browser_out = await self._publish_via_browser(content or {})
            if str(browser_out.get("status") or "") in {"published", "created", "prepared"}:
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
