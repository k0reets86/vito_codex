"""PlatformRegistry — catalog of supported platforms and capabilities."""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.logger import get_logger
from config.settings import settings
from config.paths import PROJECT_ROOT

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
        self._profiles_dir = PROJECT_ROOT / "data" / "platform_profiles"
        self._profiles: dict[str, dict] = {}
        self._init_db()
        self._load_all_profiles()

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

    def _load_all_profiles(self) -> None:
        self._profiles = {}
        try:
            self._profiles_dir.mkdir(parents=True, exist_ok=True)
            for path in sorted(self._profiles_dir.glob("*.json")):
                if path.name == "template.json":
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    pid = str(data.get("id") or path.stem).strip().lower()
                    if pid:
                        self._profiles[pid] = data
                except Exception as e:
                    logger.warning(f"Platform profile load failed for {path.name}: {e}", extra={"event": "platform_profile_load_failed"})
        except Exception as e:
            logger.warning(f"Platform profile directory load failed: {e}", extra={"event": "platform_profile_dir_load_failed"})

    def register_profile(self, profile: dict) -> str:
        platform_id = str(profile.get("id") or profile.get("name") or "").strip().lower()
        if not platform_id:
            raise ValueError("platform_profile_requires_id")
        if not profile.get("created_at"):
            profile["created_at"] = datetime.now(timezone.utc).isoformat()
        self._profiles[platform_id] = profile
        self._save_profile(platform_id, profile)
        return platform_id

    def activate_profile(self, platform_id: str) -> None:
        pid = str(platform_id or "").strip().lower()
        if pid not in self._profiles:
            raise KeyError(pid)
        self._profiles[pid]["status"] = "active"
        self._profiles[pid]["activated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_profile(pid, self._profiles[pid])

    def get_profile(self, platform_id: str) -> dict | None:
        return self._profiles.get(str(platform_id or "").strip().lower())

    def list_profiles(self, status: str | None = None, category: str | None = None) -> list[dict]:
        rows = list(self._profiles.values())
        if status:
            rows = [r for r in rows if str(r.get("status") or "").strip().lower() == str(status).strip().lower()]
        if category:
            rows = [r for r in rows if str(((r.get("overview") or {}).get("category") or "")).strip().lower() == str(category).strip().lower()]
        rows.sort(key=lambda x: str(x.get("id") or x.get("name") or ""))
        return rows

    def get_active_platforms(self, category: str | None = None) -> list[dict]:
        return self.list_profiles(status="active", category=category)

    def update_profile_field(self, platform_id: str, path: str, value) -> None:
        pid = str(platform_id or "").strip().lower()
        profile = self._profiles.get(pid)
        if not profile:
            raise KeyError(pid)
        target = profile
        parts = [p.strip() for p in str(path or "").split(".") if p.strip()]
        if not parts:
            return
        for key in parts[:-1]:
            cur = target.get(key)
            if not isinstance(cur, dict):
                cur = {}
                target[key] = cur
            target = cur
        target[parts[-1]] = value
        self._save_profile(pid, profile)

    def all_ids(self) -> list[str]:
        return sorted(self._profiles.keys())

    def _save_profile(self, platform_id: str, profile: dict) -> None:
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        path = self._profiles_dir / f"{platform_id}.json"
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

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
