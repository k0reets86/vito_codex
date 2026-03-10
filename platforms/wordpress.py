"""WordPressPlatform — WordPress REST API v2 integration.

Works with any self-hosted WordPress site with REST API enabled.
Auth: Application Password (base64 encoded user:password).
Ready to work when WORDPRESS_URL and WORDPRESS_APP_PASSWORD are set in .env.
"""

import base64
from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("wordpress", agent="wordpress")


class WordPressPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="wordpress", **kwargs)
        self._url = settings.WORDPRESS_URL.rstrip("/") if settings.WORDPRESS_URL else ""
        self._password = settings.WORDPRESS_APP_PASSWORD
        self._session: aiohttp.ClientSession | None = None

    @property
    def _api_base(self) -> str:
        return f"{self._url}/wp-json/wp/v2"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self) -> dict[str, str]:
        """Auth header using Application Password."""
        # WordPress expects "user:application_password" base64-encoded
        # The password field should contain "username:app_password"
        token = base64.b64encode(self._password.encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    async def authenticate(self) -> bool:
        """Verify connection via GET /wp-json/wp/v2/users/me."""
        if not self._url or not self._password:
            self._authenticated = False
            logger.info(
                "WordPress not configured (no URL or password)",
                extra={"event": "wp_not_configured"},
            )
            return False

        try:
            session = await self._get_session()
            async with session.get(
                f"{self._api_base}/users/me",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._authenticated = True
                    logger.info(
                        f"WordPress auth OK: {data.get('name', '?')}",
                        extra={"event": "wp_auth_ok"},
                    )
                else:
                    self._authenticated = False
                    body = await resp.text()
                    logger.warning(
                        f"WordPress auth failed: {resp.status} {body[:200]}",
                        extra={"event": "wp_auth_fail"},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"WordPress auth error: {e}", exc_info=True)
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """POST /wp-json/wp/v2/posts — create a post.

        content: {title, content (HTML), excerpt, status (draft/publish),
                  categories (list of IDs), tags (list of IDs),
                  featured_media (media ID)}
        """
        if content.get("dry_run"):
            title = content.get("title", "Untitled")
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"wordpress dry_run title={str(title)[:80]}",
                    evidence="dryrun:wordpress",
                    source="wordpress.publish",
                    evidence_dict={"platform": "wordpress", "dry_run": True, "title": title},
                )
            except Exception:
                pass
            return {
                "platform": "wordpress",
                "status": "prepared",
                "dry_run": True,
                "title": title,
            }

        if not self._url or not self._password:
            return {
                "platform": "wordpress",
                "status": "not_configured",
                "error": "Set WORDPRESS_URL and WORDPRESS_APP_PASSWORD in .env",
            }

        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return self._finalize_publish_result({"platform": "wordpress", "status": "not_authenticated"}, mode="api")

        try:
            session = await self._get_session()
            post_data = {
                "title": content.get("title", "Untitled"),
                "content": content.get("content", ""),
                "excerpt": content.get("excerpt", ""),
                "status": content.get("status", "draft"),  # draft by default — safe
            }
            if content.get("categories"):
                post_data["categories"] = content["categories"]
            if content.get("tags"):
                post_data["tags"] = content["tags"]
            if content.get("featured_media"):
                post_data["featured_media"] = content["featured_media"]

            async with session.post(
                f"{self._api_base}/posts",
                headers=self._headers(),
                json=post_data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status in (200, 201):
                    post_id = data.get("id", 0)
                    post_url = data.get("link", "")
                    logger.info(
                        f"WordPress post created: {post_id} ({post_data['status']})",
                        extra={"event": "wp_publish_ok", "context": {"post_id": post_id}},
                    )
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published" if post_data["status"] == "publish" else "draft",
                            detail=f"wordpress post_id={post_id}",
                            evidence=post_url,
                            source="wordpress.publish",
                            evidence_dict={"platform": "wordpress", "post_id": str(post_id), "url": post_url},
                        )
                    except Exception:
                        pass
                    return self._finalize_publish_result({
                        "platform": "wordpress",
                        "status": "published" if post_data["status"] == "publish" else "draft",
                        "post_id": str(post_id),
                        "url": post_url,
                    }, mode="api", artifact_flags={"post_id": bool(post_id), "url": bool(post_url)})
                error = data.get("message", str(resp.status))
                logger.warning(f"WordPress publish failed: {error}", extra={"event": "wp_publish_fail"})
                return self._finalize_publish_result({"platform": "wordpress", "status": "error", "error": error}, mode="api")

        except Exception as e:
            logger.error(f"WordPress publish error: {e}", exc_info=True)
            return self._finalize_publish_result({"platform": "wordpress", "status": "error", "error": str(e)}, mode="api")

    async def upload_media(self, file_path: str, alt_text: str = "") -> dict:
        """POST /wp-json/wp/v2/media — upload image/file."""
        if not self._authenticated:
            return {"error": "not_authenticated"}

        import os
        filename = os.path.basename(file_path)
        content_type = "image/png" if filename.endswith(".png") else "image/jpeg"

        try:
            session = await self._get_session()
            headers = self._headers()
            headers["Content-Type"] = content_type
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'

            with open(file_path, "rb") as f:
                async with session.post(
                    f"{self._api_base}/media",
                    headers=headers,
                    data=f.read(),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        return {"media_id": data.get("id"), "url": data.get("source_url", "")}
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def get_analytics(self) -> dict:
        """Get basic post stats."""
        if not self._authenticated:
            return self._finalize_analytics_result({"platform": "wordpress", "posts": 0, "views": 0}, source="api_posts")

        try:
            session = await self._get_session()
            async with session.get(
                f"{self._api_base}/posts?per_page=100&status=publish",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    posts = await resp.json()
                    return self._finalize_analytics_result({
                        "platform": "wordpress",
                        "posts": len(posts),
                        "views": 0,  # WP REST API doesn't expose views natively
                    }, source="api_posts")
        except Exception as e:
            logger.error(f"WordPress analytics error: {e}", exc_info=True)

        return self._finalize_analytics_result({"platform": "wordpress", "posts": 0, "views": 0}, source="api_posts")

    async def health_check(self) -> bool:
        if not self._url:
            return False
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
