"""ThreadsPlatform — Graph API adapter with browser-aware fallback."""

import aiohttp
from platforms.base_platform import BasePlatform
from config.settings import settings
from modules.browser_platform_runtime import browser_auth_probe, browser_extract_analytics, browser_publish_form, resolve_storage_state
from modules.execution_facts import ExecutionFacts


class ThreadsPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="threads", **kwargs)
        self._token = getattr(settings, "THREADS_ACCESS_TOKEN", "")
        self._user_id = getattr(settings, "THREADS_USER_ID", "")
        self._storage_state_path = resolve_storage_state(
            getattr(settings, "THREADS_STORAGE_STATE_FILE", ""),
            "runtime/threads_storage_state.json",
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        if self._token and self._user_id:
            self._authenticated = True
            return True
        self._authenticated = await browser_auth_probe(
            browser_agent=self.browser_agent,
            service="threads",
            url="https://www.threads.net/",
            storage_state_path=self._storage_state_path,
        )
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
            return self._finalize_publish_result({"platform": "threads", "status": "prepared", "dry_run": True}, mode="dry_run")

        text = str(content.get("text", "")).strip()
        if not text:
            return self._finalize_publish_result({"platform": "threads", "status": "error", "error": "text required"}, mode="api")
        if not self._token or not self._user_id:
            result = await browser_publish_form(
                browser_agent=self.browser_agent,
                service="threads",
                url="https://www.threads.net/",
                form_data={"title": text[:80], "text": text},
                success_status="prepared",
                title_field="text",
            )
            return self._finalize_publish_result(result, mode="browser")
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
                    return self._finalize_publish_result({"platform": "threads", "status": "error", "error": str(data)[:300]}, mode="api")
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
                    return self._finalize_publish_result({"platform": "threads", "status": "published", "post_id": post_id, "url": url}, mode="api", artifact_flags={"post_id": bool(post_id), "url": bool(url)})
                return self._finalize_publish_result({"platform": "threads", "status": "error", "error": str(data2)[:300]}, mode="api")
        except Exception as e:
            return self._finalize_publish_result({"platform": "threads", "status": "error", "error": str(e)}, mode="api")

    async def get_analytics(self) -> dict:
        if self._token and self._user_id:
            return self._finalize_analytics_result({"platform": "threads", "status": "ok", "note": "basic adapter"}, source="api_limited")
        result = await browser_extract_analytics(
            browser_agent=self.browser_agent,
            service="threads",
            url="https://www.threads.net/",
        )
        return self._finalize_analytics_result(result, source="browser_home")

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
