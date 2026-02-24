"""ExecutionFacts — store verified actions to prevent hallucinated claims."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from config.settings import settings


@dataclass
class ExecutionFact:
    id: int
    action: str
    status: str
    detail: str
    evidence: str
    source: str
    created_at: str


class ExecutionFacts:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT DEFAULT '',
                evidence TEXT DEFAULT '',
                evidence_json TEXT DEFAULT '',
                source TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        # Migrations
        try:
            conn.execute("SELECT evidence_json FROM execution_facts LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE execution_facts ADD COLUMN evidence_json TEXT DEFAULT ''")
            conn.commit()
        conn.close()

    def record(self, action: str, status: str, detail: str = "", evidence: str = "", source: str = "", evidence_dict: dict | None = None) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            """
            INSERT INTO execution_facts (action, status, detail, evidence, evidence_json, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, status, detail[:500], evidence[:1000], json.dumps(evidence_dict or {}, ensure_ascii=False)[:2000], source[:200]),
        )
        conn.commit()
        conn.close()

    def recent_exists(self, actions: list[str], hours: int = 24) -> bool:
        if not actions:
            return False
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = sqlite3.connect(self.sqlite_path)
        cur = conn.execute(
            f"""
            SELECT COUNT(*) FROM execution_facts
            WHERE created_at >= ? AND action IN ({",".join("?" for _ in actions)})
            """,
            (since, *actions),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def recent_verified_exists(self, actions: list[str], hours: int = 24) -> bool:
        if not actions:
            return False
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = sqlite3.connect(self.sqlite_path)
        cur = conn.execute(
            f"""
            SELECT COUNT(*) FROM execution_facts
            WHERE created_at >= ? AND action IN ({",".join("?" for _ in actions)})
              AND (evidence != '' OR evidence_json != '')
            """,
            (since, *actions),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def recent_facts(self, limit: int = 10) -> list[ExecutionFact]:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            """
            SELECT id, action, status, detail, evidence, source, created_at
            FROM execution_facts
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        return [ExecutionFact(*row) for row in rows]

    def facts_since(self, since_iso: str, limit: int = 20) -> list[ExecutionFact]:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            """
            SELECT id, action, status, detail, evidence, source, created_at
            FROM execution_facts
            WHERE created_at >= ?
            ORDER BY id DESC LIMIT ?
            """,
            (since_iso, limit),
        ).fetchall()
        conn.close()
        return [ExecutionFact(*row) for row in rows]
