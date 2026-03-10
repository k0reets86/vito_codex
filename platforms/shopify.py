"""ShopifyPlatform — GraphQL Admin API + browser fallback."""

from __future__ import annotations

import aiohttp

from config.settings import settings
from modules.browser_platform_runtime import (
    browser_auth_probe,
    browser_extract_analytics,
    browser_publish_form,
    resolve_storage_state,
)
from modules.execution_facts import ExecutionFacts
from platforms.base_platform import BasePlatform


class ShopifyPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="shopify", **kwargs)
        self._token = getattr(settings, "SHOPIFY_ACCESS_TOKEN", "")
        self._store_url = str(getattr(settings, "SHOPIFY_STORE_URL", "") or "").rstrip("/")
        self._storage_state_path = resolve_storage_state(
            getattr(settings, "SHOPIFY_STORAGE_STATE_FILE", ""),
            "runtime/shopify_storage_state.json",
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        if self._token and self._store_url:
            self._authenticated = True
            return True
        admin_url = f"{self._store_url}/admin" if self._store_url else "https://accounts.shopify.com/"
        self._authenticated = await browser_auth_probe(
            browser_agent=self.browser_agent,
            service="shopify",
            url=admin_url,
            storage_state_path=self._storage_state_path,
        )
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if content.get("dry_run"):
            title = str(content.get("title") or "Product")[:120]
            return self._finalize_publish_result({"platform": "shopify", "status": "prepared", "dry_run": True, "title": title}, mode="dry_run")

        if self._token and self._store_url:
            try:
                session = await self._get_session()
                mutation = """
                mutation productCreate($input: ProductInput!) {
                  productCreate(product: $input) {
                    product { id title handle status onlineStorePreviewUrl }
                    userErrors { field message }
                  }
                }
                """
                title = str(content.get("title") or "Untitled Product").strip()
                description = str(content.get("description") or content.get("content") or "").strip()
                status = "DRAFT" if str(content.get("status", "draft")).lower() != "active" else "ACTIVE"
                variables = {
                    "input": {
                        "title": title,
                        "descriptionHtml": description,
                        "status": status,
                        "productType": str(content.get("product_type") or "Digital Product").strip(),
                        "tags": list(content.get("tags") or []),
                    }
                }
                headers = {
                    "X-Shopify-Access-Token": self._token,
                    "Content-Type": "application/json",
                }
                async with session.post(
                    f"{self._store_url}/admin/api/2025-01/graphql.json",
                    json={"query": mutation, "variables": variables},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    data = await resp.json(content_type=None)
                    body = data.get("data", {}).get("productCreate", {})
                    errors = body.get("userErrors") or []
                    product = body.get("product") or {}
                    if resp.status in (200, 201) and product and not errors:
                        product_id = str(product.get("id") or "")
                        url = str(product.get("onlineStorePreviewUrl") or "")
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published" if status == "ACTIVE" else "draft",
                            detail=f"shopify product_id={product_id}",
                            evidence=url or product_id,
                            source="shopify.publish",
                            evidence_dict={"platform": "shopify", "product_id": product_id, "url": url},
                        )
                        return self._finalize_publish_result({
                            "platform": "shopify",
                            "status": "published" if status == "ACTIVE" else "draft",
                            "product_id": product_id,
                            "url": url,
                        }, mode="api", artifact_flags={"product_id": bool(product_id), "url": bool(url)})
                    return self._finalize_publish_result({"platform": "shopify", "status": "error", "error": str(errors or data)[:500]}, mode="api")
            except Exception as e:
                return self._finalize_publish_result({"platform": "shopify", "status": "error", "error": str(e)}, mode="api")

        admin_url = f"{self._store_url}/admin/products/new" if self._store_url else "https://accounts.shopify.com/"
        result = await browser_publish_form(
            browser_agent=self.browser_agent,
            service="shopify",
            url=admin_url,
            form_data={
                "title": str(content.get("title") or "Untitled Product").strip(),
                "description": str(content.get("description") or content.get("content") or "").strip(),
            },
            success_status="prepared",
        )
        return self._finalize_publish_result(result, mode="browser")

    async def get_analytics(self) -> dict:
        if self._token and self._store_url:
            return self._finalize_analytics_result({"platform": "shopify", "status": "ok", "note": "analytics endpoint pending"}, source="api_limited")
        admin_url = f"{self._store_url}/admin" if self._store_url else "https://accounts.shopify.com/"
        result = await browser_extract_analytics(browser_agent=self.browser_agent, service="shopify", url=admin_url)
        return self._finalize_analytics_result(result, source="browser_admin")

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
