"""TikTokPlatform — lightweight Content Posting API adapter (safe-first)."""

from __future__ import annotations

import aiohttp

from config.settings import settings
from modules.execution_facts import ExecutionFacts
from platforms.base_platform import BasePlatform


class TikTokPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="tiktok", **kwargs)
        self._token = getattr(settings, "TIKTOK_ACCESS_TOKEN", "")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        # Safe mode: always support dry_run and evidence-first
        if content.get("dry_run"):
            caption = str(content.get("caption", ""))[:150]
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"tiktok dry_run caption={caption}",
                    evidence="dryrun:tiktok",
                    source="tiktok.publish",
                    evidence_dict={"platform": "tiktok", "dry_run": True, "caption": caption},
                )
            except Exception:
                pass
            return {"platform": "tiktok", "status": "prepared", "dry_run": True}

        if not self._token:
            return {"platform": "tiktok", "status": "not_configured", "error": "TIKTOK_ACCESS_TOKEN missing"}

        # Minimal direct-post skeleton (requires full app approvals on TikTok side).
        # We return prepared unless real upload_url/video_url is provided.
        video_url = str(content.get("video_url", "")).strip()
        caption = str(content.get("caption", "")).strip()
        if not video_url:
            return {"platform": "tiktok", "status": "prepared", "note": "video_url required for live post"}

        try:
            session = await self._get_session()
            headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
            payload = {
                "post_info": {"title": caption[:2200], "privacy_level": "PUBLIC_TO_EVERYONE", "disable_comment": False},
                "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
            }
            async with session.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json()
                if resp.status in (200, 201):
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="prepared",
                            detail="tiktok init accepted",
                            evidence="tiktok:init",
                            source="tiktok.publish",
                            evidence_dict={"platform": "tiktok", "response": data},
                        )
                    except Exception:
                        pass
                    return {"platform": "tiktok", "status": "prepared", "response": data}
                return {"platform": "tiktok", "status": "error", "error": str(data)[:300]}
        except Exception as e:
            return {"platform": "tiktok", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        return {"platform": "tiktok", "note": "adapter skeleton"}

    async def health_check(self) -> bool:
        return bool(self._token)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
