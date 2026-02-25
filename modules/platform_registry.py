"""PlatformRegistry — catalog of supported platforms and capabilities."""

from __future__ import annotations

import sqlite3
from typing import Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("platform_registry", agent="platform_registry")


PLATFORM_CATALOG = [
    {"name": "gumroad", "type": "commerce", "capabilities": "publish,analytics", "auth_keys": "GUMROAD_API_KEY,GUMROAD_OAUTH_TOKEN"},
    {"name": "etsy", "type": "commerce", "capabilities": "publish,analytics", "auth_keys": "ETSY_API_KEY,ETSY_API_SECRET"},
    {"name": "kofi", "type": "commerce", "capabilities": "publish,analytics", "auth_keys": "KOFI_API_KEY"},
    {"name": "printful", "type": "commerce", "capabilities": "publish,analytics", "auth_keys": "PRINTFUL_API_KEY"},
    {"name": "wordpress", "type": "content", "capabilities": "publish,analytics", "auth_keys": "WORDPRESS_URL,WORDPRESS_APP_PASSWORD"},
    {"name": "medium", "type": "content", "capabilities": "publish", "auth_keys": "MEDIUM_API_KEY,MEDIUM_ACCESS_TOKEN"},
    {"name": "twitter", "type": "social", "capabilities": "publish", "auth_keys": "TWITTER_BEARER_TOKEN,TWITTER_ACCESS_TOKEN"},
    {"name": "youtube", "type": "content", "capabilities": "publish,analytics", "auth_keys": "YOUTUBE_API_KEY"},
    {"name": "substack", "type": "content", "capabilities": "publish", "auth_keys": "SUBSTACK_EMAIL,SUBSTACK_PASSWORD"},
    # Future/knowledge-only platforms (not implemented)
    {"name": "shopify", "type": "commerce", "capabilities": "publish,analytics", "auth_keys": "SHOPIFY_ACCESS_TOKEN"},
    {"name": "amazon_kdp", "type": "commerce", "capabilities": "publish", "auth_keys": "KDP_EMAIL,KDP_PASSWORD"},
    {"name": "pinterest", "type": "social", "capabilities": "publish", "auth_keys": "PINTEREST_ACCESS_TOKEN"},
    {"name": "instagram", "type": "social", "capabilities": "publish", "auth_keys": "INSTAGRAM_ACCESS_TOKEN"},
    {"name": "threads", "type": "social", "capabilities": "publish", "auth_keys": "THREADS_ACCESS_TOKEN"},
    {"name": "linkedin", "type": "social", "capabilities": "publish", "auth_keys": "LINKEDIN_ACCESS_TOKEN"},
    {"name": "tiktok", "type": "social", "capabilities": "publish", "auth_keys": "TIKTOK_ACCESS_TOKEN"},
    {"name": "facebook", "type": "social", "capabilities": "publish", "auth_keys": "FACEBOOK_PAGE_TOKEN"},
    {"name": "reddit", "type": "social", "capabilities": "publish,analytics", "auth_keys": "REDDIT_CLIENT_ID,REDDIT_CLIENT_SECRET"},
    {"name": "ebay", "type": "commerce", "capabilities": "publish,analytics", "auth_keys": "EBAY_CLIENT_ID,EBAY_CLIENT_SECRET"},
    {"name": "gumroad_browser", "type": "commerce", "capabilities": "publish", "auth_keys": "_gumroad_app_session"},
]


class PlatformRegistry:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_registry (
                    name TEXT PRIMARY KEY,
                    type TEXT DEFAULT '',
                    capabilities TEXT DEFAULT '',
                    auth_keys TEXT DEFAULT '',
                    configured INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PlatformRegistry init failed: {e}", extra={"event": "db_init_error"})

    def refresh(self) -> int:
        """Refresh registry entries based on catalog + env."""
        try:
            import os
            conn = self._get_conn()
            count = 0
            for p in PLATFORM_CATALOG:
                keys = [k.strip() for k in p.get("auth_keys", "").split(",") if k.strip()]
                configured = 1 if any(os.getenv(k, "") for k in keys) else 0
                conn.execute(
                    """
                    INSERT INTO platform_registry (name, type, capabilities, auth_keys, configured, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(name) DO UPDATE SET
                        type=excluded.type,
                        capabilities=excluded.capabilities,
                        auth_keys=excluded.auth_keys,
                        configured=excluded.configured,
                        updated_at=excluded.updated_at
                    """,
                    (p["name"], p["type"], p["capabilities"], p["auth_keys"], configured),
                )
                count += 1
            conn.commit()
            conn.close()
            return count
        except Exception:
            return 0

    def list_platforms(self, limit: int = 200) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT name, type, capabilities, configured, updated_at FROM platform_registry ORDER BY name LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "name": r[0],
                    "type": r[1],
                    "capabilities": r[2],
                    "configured": bool(r[3]),
                    "updated_at": r[4],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def stale_platforms(self, max_age_hours: int = 24) -> list[dict]:
        """Platforms whose registry record is older than max_age_hours."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT name, type, capabilities, configured, updated_at
                FROM platform_registry
                WHERE updated_at < datetime('now', ?)
                ORDER BY updated_at ASC
                """,
                (f"-{int(max_age_hours)} hour",),
            ).fetchall()
            return [
                {
                    "name": r[0],
                    "type": r[1],
                    "capabilities": r[2],
                    "configured": bool(r[3]),
                    "updated_at": r[4],
                }
                for r in rows
            ]
        finally:
            conn.close()
