"""InstagramPlatform — Graph API + browser-first fallback."""

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


class InstagramPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="instagram", **kwargs)
        self._token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "")
        self._account_id = getattr(settings, "INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
        self._storage_state_path = resolve_storage_state(
            getattr(settings, "INSTAGRAM_STORAGE_STATE_FILE", ""),
            "runtime/instagram_storage_state.json",
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        if self._token and self._account_id:
            self._authenticated = True
            return True
        self._authenticated = await browser_auth_probe(
            browser_agent=self.browser_agent,
            service="instagram",
            url="https://www.instagram.com/",
            storage_state_path=self._storage_state_path,
        )
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if content.get("dry_run"):
            caption = str(content.get("caption") or content.get("text") or "")[:180]
            return {"platform": "instagram", "status": "prepared", "dry_run": True, "caption_preview": caption}

        caption = str(content.get("caption") or content.get("text") or "").strip()
        image_url = str(content.get("image_url") or "").strip()
        if self._token and self._account_id and image_url:
            try:
                session = await self._get_session()
                params = {"image_url": image_url, "caption": caption, "access_token": self._token}
                async with session.post(
                    f"https://graph.facebook.com/v22.0/{self._account_id}/media",
                    data=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    data = await resp.json()
                    creation_id = data.get("id", "")
                    if resp.status not in (200, 201) or not creation_id:
                        return {"platform": "instagram", "status": "error", "error": str(data)[:300]}
                async with session.post(
                    f"https://graph.facebook.com/v22.0/{self._account_id}/media_publish",
                    data={"creation_id": creation_id, "access_token": self._token},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp2:
                    data2 = await resp2.json()
                    post_id = data2.get("id", "")
                    if resp2.status in (200, 201) and post_id:
                        url = f"https://www.instagram.com/p/{post_id}/"
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"instagram post_id={post_id}",
                            evidence=url,
                            source="instagram.publish",
                            evidence_dict={"platform": "instagram", "post_id": post_id, "url": url},
                        )
                        return {"platform": "instagram", "status": "published", "post_id": post_id, "url": url}
                    return {"platform": "instagram", "status": "error", "error": str(data2)[:300]}
            except Exception as e:
                return {"platform": "instagram", "status": "error", "error": str(e)}

        return await browser_publish_form(
            browser_agent=self.browser_agent,
            service="instagram",
            url="https://www.instagram.com/create/style/",
            form_data={"caption": caption or "New Instagram post", "image_url": image_url},
            success_status="prepared",
            title_field="caption",
        )

    async def get_analytics(self) -> dict:
        if self._token and self._account_id:
            return {"platform": "instagram", "status": "ok", "note": "analytics endpoint not yet wired"}
        return await browser_extract_analytics(
            browser_agent=self.browser_agent,
            service="instagram",
            url="https://www.instagram.com/",
        )

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
