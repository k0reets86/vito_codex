"""LinkedInPlatform — API + browser-first fallback."""

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


class LinkedInPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="linkedin", **kwargs)
        self._token = getattr(settings, "LINKEDIN_ACCESS_TOKEN", "")
        self._author = getattr(settings, "LINKEDIN_AUTHOR_URN", "")
        self._storage_state_path = resolve_storage_state(
            getattr(settings, "LINKEDIN_STORAGE_STATE_FILE", ""),
            "runtime/linkedin_storage_state.json",
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        if self._token and self._author:
            self._authenticated = True
            return True
        self._authenticated = await browser_auth_probe(
            browser_agent=self.browser_agent,
            service="linkedin",
            url="https://www.linkedin.com/feed/",
            storage_state_path=self._storage_state_path,
        )
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if content.get("dry_run"):
            text = str(content.get("text", ""))[:200]
            return self._finalize_publish_result({"platform": "linkedin", "status": "prepared", "dry_run": True, "text_preview": text}, mode="dry_run")

        text = str(content.get("text") or content.get("content") or "").strip()
        link = str(content.get("link") or "").strip()
        title = str(content.get("title") or "LinkedIn post").strip()
        if self._token and self._author:
            try:
                session = await self._get_session()
                payload = {
                    "author": self._author,
                    "commentary": text or title,
                    "visibility": "PUBLIC",
                    "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                    "lifecycleState": "PUBLISHED",
                    "isReshareDisabledByAuthor": False,
                }
                if link:
                    payload["content"] = {"article": {"source": link, "title": title}}
                headers = {
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                    "LinkedIn-Version": "202405",
                    "X-Restli-Protocol-Version": "2.0.0",
                }
                async with session.post(
                    "https://api.linkedin.com/rest/posts",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status in (200, 201):
                        post_id = str(data.get("id") or "")
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"linkedin post_id={post_id}",
                            evidence=post_id,
                            source="linkedin.publish",
                            evidence_dict={"platform": "linkedin", "post_id": post_id},
                        )
                        return self._finalize_publish_result({"platform": "linkedin", "status": "published", "post_id": post_id}, mode="api", artifact_flags={"post_id": bool(post_id)})
                    return self._finalize_publish_result({"platform": "linkedin", "status": "error", "error": str(data)[:300]}, mode="api")
            except Exception as e:
                return self._finalize_publish_result({"platform": "linkedin", "status": "error", "error": str(e)}, mode="api")

        result = await browser_publish_form(
            browser_agent=self.browser_agent,
            service="linkedin",
            url="https://www.linkedin.com/feed/",
            form_data={"title": title, "text": text, "link": link},
            success_status="prepared",
        )
        return self._finalize_publish_result(result, mode="browser")

    async def get_analytics(self) -> dict:
        if self._token and self._author:
            return self._finalize_analytics_result({"platform": "linkedin", "status": "ok", "note": "analytics endpoint pending"}, source="api_limited")
        result = await browser_extract_analytics(
            browser_agent=self.browser_agent,
            service="linkedin",
            url="https://www.linkedin.com/feed/",
        )
        return self._finalize_analytics_result(result, source="browser_feed")

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
