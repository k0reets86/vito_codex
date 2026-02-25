"""ThreadsPlatform — Graph API adapter (safe-first with dry-run)."""

import aiohttp
from platforms.base_platform import BasePlatform
from config.settings import settings
from modules.execution_facts import ExecutionFacts


class ThreadsPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="threads", **kwargs)
        self._token = getattr(settings, "THREADS_ACCESS_TOKEN", "")
        self._user_id = getattr(settings, "THREADS_USER_ID", "")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token and self._user_id)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if content.get("dry_run"):
            text = str(content.get("text", ""))[:150]
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"threads dry_run text={text}",
                    evidence="dryrun:threads",
                    source="threads.publish",
                    evidence_dict={"platform": "threads", "dry_run": True, "text": text},
                )
            except Exception:
                pass
            return {"platform": "threads", "status": "prepared", "dry_run": True}

        if not self._token:
            return {"platform": "threads", "status": "not_configured", "error": "THREADS_ACCESS_TOKEN missing"}
        if not self._user_id:
            return {"platform": "threads", "status": "not_configured", "error": "THREADS_USER_ID missing"}
        text = str(content.get("text", "")).strip()
        if not text:
            return {"platform": "threads", "status": "error", "error": "text required"}
        try:
            session = await self._get_session()
            params = {"media_type": "TEXT", "text": text, "access_token": self._token}
            async with session.post(
                f"https://graph.threads.net/v1.0/{self._user_id}/threads",
                data=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json()
                creation_id = data.get("id", "")
                if resp.status not in (200, 201) or not creation_id:
                    return {"platform": "threads", "status": "error", "error": str(data)[:300]}
            params2 = {"creation_id": creation_id, "access_token": self._token}
            async with session.post(
                f"https://graph.threads.net/v1.0/{self._user_id}/threads_publish",
                data=params2,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp2:
                data2 = await resp2.json()
                post_id = data2.get("id", "")
                if resp2.status in (200, 201) and post_id:
                    url = f"https://www.threads.net/t/{post_id}"
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"threads post_id={post_id}",
                            evidence=url,
                            source="threads.publish",
                            evidence_dict={"platform": "threads", "post_id": post_id, "url": url},
                        )
                    except Exception:
                        pass
                    return {"platform": "threads", "status": "published", "post_id": post_id, "url": url}
                return {"platform": "threads", "status": "error", "error": str(data2)[:300]}
        except Exception as e:
            return {"platform": "threads", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        return {"platform": "threads", "note": "basic adapter"}

    async def health_check(self) -> bool:
        return bool(self._token and self._user_id)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
