"""InstagramPlatform — Graph API + browser-first fallback."""

from __future__ import annotations

import aiohttp
import tempfile
from pathlib import Path

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
        self._username = getattr(settings, "INSTAGRAM_USERNAME", "")
        self._password = getattr(settings, "INSTAGRAM_PASSWORD", "")
        self._storage_state_path = resolve_storage_state(
            getattr(settings, "INSTAGRAM_STORAGE_STATE_FILE", ""),
            "runtime/instagram_storage_state.json",
        )
        self._instagrapi_session_path = Path(
            getattr(settings, "INSTAGRAM_SESSION_FILE", "") or "runtime/instagram_instagrapi_session.json"
        )
        self._session: aiohttp.ClientSession | None = None
        self._instagrapi_client = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _download_temp_image(self, image_url: str) -> str:
        session = await self._get_session()
        async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            suffix = ".jpg"
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            if "png" in ctype:
                suffix = ".png"
            fd, path = tempfile.mkstemp(prefix="instagram_publish_", suffix=suffix)
            with open(fd, "wb", closefd=True) as fh:
                fh.write(await resp.read())
            return path

    def _get_instagrapi_client(self):
        if self._instagrapi_client is not None:
            return self._instagrapi_client
        if not (self._username and self._password):
            return None
        try:
            from instagrapi import Client  # type: ignore
        except Exception:
            return None
        client = Client()
        self._instagrapi_session_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self._instagrapi_session_path.exists():
                client.load_settings(str(self._instagrapi_session_path))
        except Exception:
            pass
        self._instagrapi_client = client
        return client

    def _save_instagrapi_session(self, client) -> None:
        try:
            self._instagrapi_session_path.parent.mkdir(parents=True, exist_ok=True)
            client.dump_settings(str(self._instagrapi_session_path))
        except Exception:
            pass

    async def _instagrapi_authenticate(self) -> bool:
        client = self._get_instagrapi_client()
        if client is None:
            return False
        try:
            login_ok = client.login(self._username, self._password)
            if login_ok:
                self._save_instagrapi_session(client)
                self._authenticated = True
                return True
        except Exception:
            try:
                if client.get_timeline_feed():
                    self._authenticated = True
                    return True
            except Exception:
                return False
        return False

    async def authenticate(self) -> bool:
        if self._token and self._account_id:
            self._authenticated = True
            return True
        if await self._instagrapi_authenticate():
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
            return self._finalize_publish_result({"platform": "instagram", "status": "prepared", "dry_run": True, "caption_preview": caption}, mode="dry_run")

        caption = str(content.get("caption") or content.get("text") or "").strip()
        image_url = str(content.get("image_url") or "").strip()
        image_path = str(content.get("image_path") or "").strip()
        if not image_path and image_url:
            try:
                image_path = await self._download_temp_image(image_url)
            except Exception:
                image_path = ""

        client = self._get_instagrapi_client()
        if client and image_path:
            try:
                media = client.photo_upload(Path(image_path), caption or "New Instagram post")
                media_pk = str(getattr(media, "pk", "") or getattr(media, "id", "") or "").strip()
                media_code = str(getattr(media, "code", "") or "").strip()
                self._save_instagrapi_session(client)
                url = f"https://www.instagram.com/p/{media_code}/" if media_code else ""
                ExecutionFacts().record(
                    action="platform:publish",
                    status="published",
                    detail=f"instagram media_pk={media_pk or media_code}",
                    evidence=url or media_pk,
                    source="instagram.publish",
                    evidence_dict={"platform": "instagram", "media_pk": media_pk, "code": media_code, "url": url},
                )
                return self._finalize_publish_result(
                    {"platform": "instagram", "status": "published", "media_pk": media_pk, "code": media_code, "url": url},
                    mode="instagrapi",
                    artifact_flags={"image": bool(image_path), "caption": bool(caption), "url": bool(url) or bool(media_pk)},
                )
            except Exception as e:
                if not (self._token and self._account_id):
                    return self._finalize_publish_result({"platform": "instagram", "status": "error", "error": str(e)}, mode="instagrapi")

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
                        return self._finalize_publish_result({"platform": "instagram", "status": "error", "error": str(data)[:300]}, mode="api")
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
                        return self._finalize_publish_result({"platform": "instagram", "status": "published", "post_id": post_id, "url": url}, mode="api", artifact_flags={"post_id": bool(post_id), "url": bool(url)})
                    return self._finalize_publish_result({"platform": "instagram", "status": "error", "error": str(data2)[:300]}, mode="api")
            except Exception as e:
                return self._finalize_publish_result({"platform": "instagram", "status": "error", "error": str(e)}, mode="api")

        result = await browser_publish_form(
            browser_agent=self.browser_agent,
            service="instagram",
            url="https://www.instagram.com/create/style/",
            form_data={"caption": caption or "New Instagram post", "image_url": image_url},
            success_status="prepared",
            title_field="caption",
        )
        return self._finalize_publish_result(result, mode="browser")

    async def get_analytics(self) -> dict:
        if self._token and self._account_id:
            return self._finalize_analytics_result({"platform": "instagram", "status": "ok", "note": "analytics endpoint not yet wired"}, source="api_limited")
        result = await browser_extract_analytics(
            browser_agent=self.browser_agent,
            service="instagram",
            url="https://www.instagram.com/",
        )
        return self._finalize_analytics_result(result, source="browser_home")

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
