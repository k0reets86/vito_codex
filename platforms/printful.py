"""PrintfulPlatform — интеграция с Printful REST API (print-on-demand)."""

import json
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
            # If API key is available, prefer trying API path first even in browser mode.
            if not self._api_key:
                return {
                    "platform": "printful",
                    "status": "needs_browser_flow",
                    "error": "Printful browser publish path requires dedicated UI runner. Auth can be captured via scripts/printful_auth_helper.py.",
                    "storage_state": str(self._storage_state_path),
                }
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
