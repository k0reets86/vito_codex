"""MediumPlatform — Medium API integration.

Medium API: https://github.com/Medium/medium-api-docs
Auth: Integration token (Bearer).
Ready to work when MEDIUM_TOKEN is set in .env.
"""

from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform

logger = get_logger("medium", agent="medium")
API_BASE = "https://api.medium.com/v1"


class MediumPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="medium", **kwargs)
        self._token = settings.MEDIUM_TOKEN
        self._user_id: str = ""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def authenticate(self) -> bool:
        """GET /v1/me — verify token and get user ID."""
        if not self._token:
            self._authenticated = False
            logger.info("Medium not configured (no token)", extra={"event": "medium_not_configured"})
            return False

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/me",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("data", {})
                    self._user_id = user.get("id", "")
                    self._authenticated = True
                    logger.info(
                        f"Medium auth OK: {user.get('name', '?')}",
                        extra={"event": "medium_auth_ok", "context": {"username": user.get("username")}},
                    )
                else:
                    self._authenticated = False
                    body = await resp.text()
                    logger.warning(
                        f"Medium auth failed: {resp.status} {body[:200]}",
                        extra={"event": "medium_auth_fail"},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Medium auth error: {e}", exc_info=True)
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """POST /v1/users/{userId}/posts — create a story.

        content: {title, content (HTML or markdown), contentFormat (html/markdown),
                  tags (list), publishStatus (draft/public/unlisted),
                  canonicalUrl (optional)}
        """
        if not self._token:
            return self._finalize_publish_result({
                "platform": "medium",
                "status": "not_configured",
                "error": "Set MEDIUM_TOKEN in .env (get from medium.com/me/settings)",
            }, mode="api")

        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return self._finalize_publish_result({"platform": "medium", "status": "not_authenticated"}, mode="api")

        try:
            session = await self._get_session()
            post_data = {
                "title": content.get("title", "Untitled"),
                "content": content.get("content", ""),
                "contentFormat": content.get("contentFormat", "markdown"),
                "publishStatus": content.get("publishStatus", "draft"),
            }
            if content.get("tags"):
                post_data["tags"] = content["tags"][:5]  # Medium max 5 tags
            if content.get("canonicalUrl"):
                post_data["canonicalUrl"] = content["canonicalUrl"]

            async with session.post(
                f"{API_BASE}/users/{self._user_id}/posts",
                headers=self._headers(),
                json=post_data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status in (200, 201):
                    story = data.get("data", {})
                    story_id = story.get("id", "")
                    story_url = story.get("url", "")
                    logger.info(
                        f"Medium story created: {story_id}",
                        extra={"event": "medium_publish_ok", "context": {"story_id": story_id}},
                    )
                    return self._finalize_publish_result({
                        "platform": "medium",
                        "status": "published" if post_data["publishStatus"] == "public" else "draft",
                        "story_id": story_id,
                        "url": story_url,
                    }, mode="api", artifact_flags={"story_id": bool(story_id), "url": bool(story_url)})
                error_msg = data.get("errors", [{}])[0].get("message", str(resp.status)) if data.get("errors") else str(resp.status)
                logger.warning(f"Medium publish failed: {error_msg}", extra={"event": "medium_publish_fail"})
                return self._finalize_publish_result({"platform": "medium", "status": "error", "error": error_msg}, mode="api")

        except Exception as e:
            logger.error(f"Medium publish error: {e}", exc_info=True)
            return self._finalize_publish_result({"platform": "medium", "status": "error", "error": str(e)}, mode="api")

    async def get_analytics(self) -> dict:
        """Medium API doesn't provide analytics. Returns basic info."""
        # Medium's public API is very limited — no analytics endpoint
        return self._finalize_analytics_result({
            "platform": "medium",
            "stories": 0,
            "views": 0,
            "claps": 0,
            "note": "Medium API does not expose analytics. Use medium.com/me/stats.",
        }, source="api_limited")

    async def health_check(self) -> bool:
        if not self._token:
            return False
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
