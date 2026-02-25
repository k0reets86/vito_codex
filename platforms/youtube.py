"""YouTube Platform — интеграция с YouTube Data API v3.

Только чтение: поиск трендов, аналитика каналов. Не публикация.
"""

from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("youtube", agent="youtube")
API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubePlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="youtube", **kwargs)
        self._api_key = getattr(settings, "GOOGLE_API_KEY", "")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        """Проверка API ключа через простой запрос."""
        if not self._api_key:
            self._authenticated = False
            return False
        try:
            session = await self._get_session()
            params = {"part": "snippet", "chart": "mostPopular", "maxResults": 1, "key": self._api_key}
            async with session.get(f"{API_BASE}/videos", params=params) as resp:
                self._authenticated = resp.status == 200
                return self._authenticated
        except Exception as e:
            logger.error(f"YouTube auth error: {e}", extra={"event": "youtube_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Safe-first publish adapter.

        Full resumable upload flow requires OAuth client setup.
        In this phase we support evidence-producing dry_run and prepared mode.
        """
        if content.get("dry_run"):
            title = str(content.get("title", ""))[:120]
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"youtube dry_run title={title}",
                    evidence="dryrun:youtube",
                    source="youtube.publish",
                    evidence_dict={"platform": "youtube", "dry_run": True, "title": title},
                )
            except Exception:
                pass
            return {"platform": "youtube", "status": "prepared", "dry_run": True}
        return {"platform": "youtube", "status": "not_supported", "reason": "upload flow requires OAuth upload scope"}

    async def get_analytics(self) -> dict:
        """Получение трендовых видео."""
        return await self.search_trending()

    async def search_trending(self, region: str = "US", max_results: int = 10) -> dict:
        """GET /videos?chart=mostPopular — трендовые видео."""
        if not self._api_key:
            return {"platform": "youtube", "videos": []}
        try:
            session = await self._get_session()
            params = {
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": region,
                "maxResults": max_results,
                "key": self._api_key,
            }
            async with session.get(f"{API_BASE}/videos", params=params) as resp:
                data = await resp.json()
                videos = [
                    {
                        "title": item["snippet"]["title"],
                        "channel": item["snippet"]["channelTitle"],
                        "views": int(item["statistics"].get("viewCount", 0)),
                        "likes": int(item["statistics"].get("likeCount", 0)),
                        "published_at": item["snippet"]["publishedAt"],
                    }
                    for item in data.get("items", [])
                ]
                return {"platform": "youtube", "region": region, "videos": videos}
        except Exception as e:
            logger.error(f"YouTube trending error: {e}", extra={"event": "youtube_trending_error"})
            return {"platform": "youtube", "videos": [], "error": str(e)}

    async def search_videos(self, query: str, max_results: int = 10) -> list[dict]:
        """GET /search — поиск видео."""
        if not self._api_key:
            return []
        try:
            session = await self._get_session()
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": max_results,
                "order": "relevance",
                "key": self._api_key,
            }
            async with session.get(f"{API_BASE}/search", params=params) as resp:
                data = await resp.json()
                return [
                    {
                        "video_id": item["id"]["videoId"],
                        "title": item["snippet"]["title"],
                        "channel": item["snippet"]["channelTitle"],
                        "description": item["snippet"]["description"][:200],
                    }
                    for item in data.get("items", [])
                ]
        except Exception as e:
            logger.error(f"YouTube search error: {e}", extra={"event": "youtube_search_error"})
            return []

    async def get_channel_stats(self, channel_id: str) -> dict:
        """GET /channels — статистика канала."""
        if not self._api_key:
            return {}
        try:
            session = await self._get_session()
            params = {
                "part": "statistics,snippet",
                "id": channel_id,
                "key": self._api_key,
            }
            async with session.get(f"{API_BASE}/channels", params=params) as resp:
                data = await resp.json()
                items = data.get("items", [])
                if not items:
                    return {}
                item = items[0]
                stats = item["statistics"]
                return {
                    "channel": item["snippet"]["title"],
                    "subscribers": int(stats.get("subscriberCount", 0)),
                    "views": int(stats.get("viewCount", 0)),
                    "videos": int(stats.get("videoCount", 0)),
                }
        except Exception as e:
            logger.error(f"YouTube channel stats error: {e}", extra={"event": "youtube_channel_error"})
            return {}

    async def health_check(self) -> bool:
        return bool(self._api_key)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
