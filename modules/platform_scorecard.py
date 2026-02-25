"""Platform scorecard for production readiness/evidence coverage."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from config.settings import settings


@dataclass
class PlatformScore:
    platform: str
    configured: bool
    evidence_count_30d: int
    success_count_30d: int
    fail_count_30d: int
    readiness_score: int
    note: str


class PlatformScorecard:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _env_configured(self, platform: str) -> bool:
        p = platform.lower()
        checks = {
            "gumroad": bool(settings.GUMROAD_API_KEY or settings.GUMROAD_OAUTH_TOKEN),
            "etsy": bool(settings.ETSY_KEYSTRING),
            "wordpress": bool(settings.WORDPRESS_URL and settings.WORDPRESS_APP_PASSWORD),
            "twitter": bool(settings.TWITTER_BEARER_TOKEN and settings.TWITTER_CONSUMER_KEY),
            "kofi": bool(settings.KOFI_API_KEY and settings.KOFI_PAGE_ID),
            "printful": bool(settings.PRINTFUL_API_KEY),
            "threads": bool(getattr(settings, "THREADS_ACCESS_TOKEN", "") and getattr(settings, "THREADS_USER_ID", "")),
            "youtube": bool(getattr(settings, "GOOGLE_API_KEY", "")),
            "reddit": bool(getattr(settings, "REDDIT_CLIENT_ID", "") and getattr(settings, "REDDIT_CLIENT_SECRET", "")),
            "tiktok": bool(getattr(settings, "TIKTOK_ACCESS_TOKEN", "")),
        }
        return checks.get(p, False)

    def _fact_counts(self, platform: str, days: int = 30) -> tuple[int, int, int]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT status, evidence
                FROM execution_facts
                WHERE action IN ('platform:publish', 'platform:publish_job')
                  AND datetime(created_at) >= datetime('now', ?)
                  AND lower(detail) LIKE ?
                """,
                (f"-{int(days)} days", f"{platform.lower()}%"),
            ).fetchall()
            success = 0
            fail = 0
            evidence = 0
            for r in rows:
                st = str(r["status"] or "").lower()
                ev = str(r["evidence"] or "").strip()
                if st in {"published", "created", "draft", "prepared", "completed", "success"}:
                    success += 1
                if st in {"error", "failed", "timeout", "daily_limit", "need_cookie", "not_authenticated"}:
                    fail += 1
                if ev:
                    evidence += 1
            return evidence, success, fail
        finally:
            conn.close()

    def score(self, platforms: list[str], days: int = 30) -> list[dict]:
        out: list[dict] = []
        for p in platforms:
            configured = self._env_configured(p)
            evidence, success, fail = self._fact_counts(p, days=days)
            score = 0
            if configured:
                score += 30
            score += min(40, success * 5)
            score += min(30, evidence * 5)
            score -= min(35, fail * 3)
            score = max(0, min(100, score))
            note = "ready" if score >= 70 else ("partial" if score >= 40 else "weak")
            row = PlatformScore(
                platform=p,
                configured=configured,
                evidence_count_30d=evidence,
                success_count_30d=success,
                fail_count_30d=fail,
                readiness_score=score,
                note=note,
            )
            out.append(row.__dict__)
        out.sort(key=lambda x: x["readiness_score"], reverse=True)
        return out
