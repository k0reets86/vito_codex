"""RSSRegistry — manage RSS/news sources for TrendScout."""

from __future__ import annotations

import sqlite3
from typing import Optional

from config.settings import settings
from config.logger import get_logger

logger = get_logger("rss_registry", agent="rss_registry")


DEFAULT_RSS = [
    # fallback to env-configured RSS if present
    "{REDDIT_RSS_ENTREPRENEUR}",
    "{REDDIT_RSS_PASSIVE}",
    "{REDDIT_RSS_ECOMMERCE}",
]


class RSSRegistry:
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
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"RSSRegistry init failed: {e}", extra={"event": "db_init_error"})

    def list_sources(self, limit: int = 200) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, name, url, enabled, updated_at FROM rss_sources ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {"id": r[0], "name": r[1], "url": r[2], "enabled": bool(r[3]), "updated_at": r[4]}
                for r in rows
            ]
        finally:
            conn.close()

    def add_source(self, name: str, url: str) -> int:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO rss_sources (name, url, enabled, updated_at) VALUES (?, ?, 1, datetime('now'))",
                (name[:100], url[:500]),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def toggle_source(self, source_id: int, enabled: bool) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE rss_sources SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
                (1 if enabled else 0, source_id),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_source(self, source_id: int) -> None:
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM rss_sources WHERE id = ?", (source_id,))
            conn.commit()
        finally:
            conn.close()

    def get_enabled_urls(self) -> list[str]:
        sources = [s for s in self.list_sources() if s.get("enabled")]
        urls = [s["url"] for s in sources if s.get("url")]
        if urls:
            return urls
        # fallback to settings-defined RSS
        out = []
        for key in ("REDDIT_RSS_ENTREPRENEUR", "REDDIT_RSS_PASSIVE", "REDDIT_RSS_ECOMMERCE"):
            val = getattr(settings, key, "")
            if val:
                out.append(val)
        return out
