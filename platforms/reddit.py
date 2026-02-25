"""RedditPlatform — lightweight Reddit publish adapter (SDK-pack step)."""

from __future__ import annotations

import aiohttp

from config.logger import get_logger
from config.settings import settings
from modules.execution_facts import ExecutionFacts
from platforms.base_platform import BasePlatform

logger = get_logger("reddit", agent="reddit")


class RedditPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="reddit", **kwargs)
        self._client_id = getattr(settings, "REDDIT_CLIENT_ID", "")
        self._client_secret = getattr(settings, "REDDIT_CLIENT_SECRET", "")
        self._username = getattr(settings, "REDDIT_USERNAME", "")
        self._password = getattr(settings, "REDDIT_PASSWORD", "")
        self._user_agent = getattr(settings, "REDDIT_USER_AGENT", "vito-bot/0.3")
        self._token = ""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        if not (self._client_id and self._client_secret and self._username and self._password):
            self._authenticated = False
            return False
        try:
            session = await self._get_session()
            auth = aiohttp.BasicAuth(self._client_id, self._client_secret)
            data = {"grant_type": "password", "username": self._username, "password": self._password}
            headers = {"User-Agent": self._user_agent}
            async with session.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                payload = await resp.json()
                token = payload.get("access_token", "")
                self._token = token
                self._authenticated = bool(token)
                return self._authenticated
        except Exception as e:
            logger.warning(f"Reddit auth error: {e}", extra={"event": "reddit_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        if content.get("dry_run"):
            title = str(content.get("title", ""))
            subreddit = str(content.get("subreddit", "test"))
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"reddit dry_run subreddit={subreddit} title={title[:80]}",
                    evidence="dryrun:reddit",
                    source="reddit.publish",
                    evidence_dict={"platform": "reddit", "dry_run": True, "subreddit": subreddit, "title": title},
                )
            except Exception:
                pass
            return {"platform": "reddit", "status": "prepared", "dry_run": True, "subreddit": subreddit}

        if not self._authenticated:
            ok = await self.authenticate()
            if not ok:
                return {"platform": "reddit", "status": "not_authenticated"}

        subreddit = str(content.get("subreddit", "")).strip()
        title = str(content.get("title", "")).strip()
        body = str(content.get("text", "")).strip()
        if not subreddit or not title:
            return {"platform": "reddit", "status": "error", "error": "subreddit/title required"}

        try:
            session = await self._get_session()
            headers = {"Authorization": f"Bearer {self._token}", "User-Agent": self._user_agent}
            data = {"sr": subreddit, "title": title, "kind": "self", "text": body, "resubmit": "true", "api_type": "json"}
            async with session.post(
                "https://oauth.reddit.com/api/submit",
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                payload = await resp.json()
                errs = (((payload or {}).get("json") or {}).get("errors") or [])
                if resp.status in (200, 201) and not errs:
                    try:
                        url = f"https://reddit.com/r/{subreddit}/new"
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"reddit subreddit={subreddit} title={title[:80]}",
                            evidence=url,
                            source="reddit.publish",
                            evidence_dict={"platform": "reddit", "subreddit": subreddit, "title": title},
                        )
                    except Exception:
                        pass
                    return {"platform": "reddit", "status": "published", "url": url}
                return {"platform": "reddit", "status": "error", "error": str(errs)[:300]}
        except Exception as e:
            return {"platform": "reddit", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        return {"platform": "reddit", "note": "basic adapter"}

    async def health_check(self) -> bool:
        return bool(self._client_id and self._client_secret)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
