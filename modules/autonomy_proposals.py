from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from config.settings import settings


class AutonomyProposalStore:
    """Persistent lifecycle store for curriculum/scout/evolver proposals."""

    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS autonomy_proposals (
                    proposal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_key TEXT UNIQUE NOT NULL,
                    source_agent TEXT NOT NULL,
                    proposal_kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT DEFAULT '{}',
                    status TEXT DEFAULT 'proposed',
                    score REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    decision_at TEXT DEFAULT '',
                    executed_at TEXT DEFAULT '',
                    execution_notes TEXT DEFAULT ''
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_batch(self, source_agent: str, proposal_kind: str, proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        out: list[dict[str, Any]] = []
        ordered_keys: list[str] = []
        conn = self._conn()
        try:
            for idx, proposal in enumerate(proposals or [], start=1):
                payload = dict(proposal or {})
                title = str(payload.get("title") or f"{proposal_kind}_{idx}").strip()[:240]
                key = self._make_key(source_agent, proposal_kind, title, payload)
                ordered_keys.append(key)
                score = float(
                    payload.get("confidence")
                    or payload.get("proposal_score")
                    or payload.get("expected_revenue")
                    or 0.0
                )
                conn.execute(
                    """
                    INSERT INTO autonomy_proposals
                    (proposal_key, source_agent, proposal_kind, title, payload_json, status, score, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)
                    ON CONFLICT(proposal_key) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        score=excluded.score,
                        updated_at=excluded.updated_at
                    """,
                    (
                        key,
                        str(source_agent or "").strip(),
                        str(proposal_kind or "").strip(),
                        title,
                        json.dumps(payload, ensure_ascii=False),
                        score,
                        now,
                    ),
                )
            conn.commit()
            if ordered_keys:
                placeholders = ",".join("?" for _ in ordered_keys)
                rows = conn.execute(
                    f"""
                    SELECT * FROM autonomy_proposals
                    WHERE proposal_key IN ({placeholders})
                    """,
                    tuple(ordered_keys),
                ).fetchall()
                rows_by_key = {str(r["proposal_key"]): self._row_to_dict(r) for r in rows}
                out = [rows_by_key[key] for key in ordered_keys if key in rows_by_key]
        finally:
            conn.close()
        return out

    def list_open(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM autonomy_proposals
                WHERE status IN ('proposed', 'approved', 'deferred')
                ORDER BY score DESC, datetime(updated_at) DESC, proposal_id DESC
                LIMIT ?
                """,
                (int(limit or 10),),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get(self, proposal_id: int) -> dict[str, Any] | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM autonomy_proposals WHERE proposal_id = ? LIMIT 1",
                (int(proposal_id),),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def get_by_index(self, index: int, *, limit: int = 10) -> dict[str, Any] | None:
        items = self.list_open(limit=limit)
        if 1 <= int(index) <= len(items):
            return items[int(index) - 1]
        return None

    def mark_status(self, proposal_id: int, status: str, note: str = "") -> dict[str, Any] | None:
        status = str(status or "").strip().lower()
        if status not in {"approved", "deferred", "rejected", "executed"}:
            raise ValueError("invalid_proposal_status")
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            extra_field = "decision_at"
            if status == "executed":
                extra_field = "executed_at"
            conn.execute(
                f"""
                UPDATE autonomy_proposals
                SET status = ?,
                    updated_at = ?,
                    {extra_field} = ?,
                    execution_notes = CASE
                        WHEN ? = '' THEN execution_notes
                        ELSE ?
                    END
                WHERE proposal_id = ?
                """,
                (status, now, now, str(note or "").strip(), str(note or "").strip(), int(proposal_id)),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(proposal_id)

    def list_recent(self, limit: int = 25) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM autonomy_proposals ORDER BY datetime(updated_at) DESC, proposal_id DESC LIMIT ?",
                (int(limit or 25),),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def _make_key(self, source_agent: str, proposal_kind: str, title: str, payload: dict[str, Any]) -> str:
        blob = json.dumps(
            {
                "source_agent": str(source_agent or "").strip(),
                "proposal_kind": str(proposal_kind or "").strip(),
                "title": str(title or "").strip(),
                "type": str(payload.get("type") or "").strip(),
                "why": str(payload.get("why") or payload.get("rationale") or "").strip()[:240],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload_json") or "{}")
        except Exception:
            item["payload"] = {}
        return item
