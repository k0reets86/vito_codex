"""A/B content experiments runtime for marketing and social variants."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from config.settings import settings


class ContentExperimentEngine:
    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._conn: sqlite3.Connection | None = None
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.sqlite_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_tables(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS content_experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family TEXT NOT NULL,
                subject TEXT NOT NULL,
                platform TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                winner_variant TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS content_experiment_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                variant_key TEXT NOT NULL,
                content_json TEXT NOT NULL,
                impressions INTEGER NOT NULL DEFAULT 0,
                clicks INTEGER NOT NULL DEFAULT 0,
                conversions INTEGER NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0,
                UNIQUE(experiment_id, variant_key)
            )
            """
        )
        conn.commit()

    def create_experiment(self, *, family: str, subject: str, platform: str, variants: list[str]) -> dict[str, Any]:
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO content_experiments (family, subject, platform) VALUES (?, ?, ?)",
            (str(family or "content"), str(subject or "").strip(), str(platform or "generic").strip()),
        )
        experiment_id = int(cur.lastrowid)
        normalized = []
        for idx, variant in enumerate(variants, start=1):
            key = f"v{idx}"
            payload = {"text": str(variant or "").strip()}
            conn.execute(
                """
                INSERT INTO content_experiment_variants (experiment_id, variant_key, content_json)
                VALUES (?, ?, ?)
                """,
                (experiment_id, key, json.dumps(payload, ensure_ascii=False)),
            )
            normalized.append({"variant_key": key, "text": payload["text"]})
        conn.commit()
        return {
            "experiment_id": experiment_id,
            "family": family,
            "subject": subject,
            "platform": platform,
            "variants": normalized,
            "status": "open",
        }

    def record_outcome(
        self,
        experiment_id: int,
        variant_key: str,
        *,
        impressions: int = 0,
        clicks: int = 0,
        conversions: int = 0,
    ) -> dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT impressions, clicks, conversions FROM content_experiment_variants
            WHERE experiment_id = ? AND variant_key = ?
            """,
            (int(experiment_id), str(variant_key)),
        ).fetchone()
        if not row:
            raise ValueError("content_experiment_variant_not_found")
        new_impressions = int(row["impressions"] or 0) + max(0, int(impressions or 0))
        new_clicks = int(row["clicks"] or 0) + max(0, int(clicks or 0))
        new_conversions = int(row["conversions"] or 0) + max(0, int(conversions or 0))
        ctr = (new_clicks / new_impressions) if new_impressions else 0.0
        cvr = (new_conversions / new_clicks) if new_clicks else 0.0
        score = round((ctr * 0.4) + (cvr * 0.6), 6)
        conn.execute(
            """
            UPDATE content_experiment_variants
            SET impressions = ?, clicks = ?, conversions = ?, score = ?
            WHERE experiment_id = ? AND variant_key = ?
            """,
            (new_impressions, new_clicks, new_conversions, score, int(experiment_id), str(variant_key)),
        )
        conn.commit()
        return {
            "experiment_id": int(experiment_id),
            "variant_key": str(variant_key),
            "impressions": new_impressions,
            "clicks": new_clicks,
            "conversions": new_conversions,
            "score": score,
        }

    def choose_winner(self, experiment_id: int) -> dict[str, Any]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT variant_key, content_json, impressions, clicks, conversions, score
            FROM content_experiment_variants
            WHERE experiment_id = ?
            ORDER BY score DESC, conversions DESC, clicks DESC, impressions DESC
            """,
            (int(experiment_id),),
        ).fetchall()
        if not rows:
            raise ValueError("content_experiment_not_found")
        winner = dict(rows[0])
        conn.execute(
            "UPDATE content_experiments SET status = 'closed', winner_variant = ? WHERE id = ?",
            (str(winner["variant_key"]), int(experiment_id)),
        )
        conn.commit()
        return {
            "experiment_id": int(experiment_id),
            "winner_variant": str(winner["variant_key"]),
            "winner_score": float(winner["score"] or 0.0),
            "winner_text": json.loads(str(winner["content_json"] or "{}")).get("text", ""),
        }
