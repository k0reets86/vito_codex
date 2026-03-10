from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from config.paths import root_path


class ConversationMemory:
    def __init__(self, path: Path | str | None = None, limit: int = 50) -> None:
        self.path = Path(path or root_path("runtime", "conversation_history.json"))
        self.limit = limit
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = self.path.with_suffix(f"{self.path.suffix}.sqlite3")
        self._init_db()
        if self._db_is_empty():
            self._migrate_from_json_snapshot()
        self._sync_json_snapshot()

    @staticmethod
    def _compact_payload(payload: dict) -> dict:
        compact = {
            "session_id": str(payload.get("session_id") or "default"),
            "role": str(payload.get("role") or "user"),
            "text": str(payload.get("text") or "")[:4000],
            "intent": str(payload.get("intent") or "")[:200],
            "timestamp": str(payload.get("timestamp") or "")[:100],
        }
        extras = {
            k: v
            for k, v in dict(payload or {}).items()
            if k not in {"session_id", "role", "text", "intent", "timestamp"}
        }
        if extras:
            compact["payload_meta"] = {
                "keys": sorted(str(k) for k in extras.keys())[:20],
                "raw_size": len(json.dumps(extras, ensure_ascii=False, default=str)),
            }
        return compact

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    intent TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_id_id "
                "ON conversation_messages(session_id, id)"
            )
            conn.commit()

    def _db_is_empty(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM conversation_messages").fetchone()
            return int(row["c"] or 0) == 0

    @staticmethod
    def _normalize_session(session_id: str | None) -> str:
        sid = str(session_id or "default").strip()
        return sid or "default"

    def _load_snapshot_rows(self) -> list[dict]:
        try:
            if not self.path.exists():
                return []
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [dict(row) for row in data if isinstance(row, dict)]
            if isinstance(data, dict):
                rows: list[dict] = []
                sessions = data.get("sessions") or {}
                if isinstance(sessions, dict):
                    for session_id, items in sessions.items():
                        if not isinstance(items, list):
                            continue
                        for row in items:
                            if not isinstance(row, dict):
                                continue
                            payload = dict(row)
                            payload["session_id"] = self._normalize_session(payload.get("session_id") or session_id)
                            rows.append(payload)
                return rows
        except Exception:
            pass
        return []

    def _migrate_from_json_snapshot(self) -> None:
        rows = self._load_snapshot_rows()
        if not rows:
            return
        with self._connect() as conn:
            for row in rows:
                payload = dict(row)
                sid = self._normalize_session(payload.get("session_id"))
                role = str(payload.get("role") or "").strip() or "user"
                text = str(payload.get("text") or "")
                intent = str(payload.get("intent") or "")
                timestamp = str(payload.get("timestamp") or "")
                conn.execute(
                    """
                    INSERT INTO conversation_messages (
                        session_id, role, text, intent, timestamp, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sid,
                        role,
                        text,
                        intent,
                        timestamp,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def _session_rows(self, session_id: str) -> list[dict]:
        sid = self._normalize_session(session_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM conversation_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (sid,),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                payload["session_id"] = sid
                out.append(payload)
        return out

    def _trim_session(self, session_id: str) -> None:
        sid = self._normalize_session(session_id)
        with self._connect() as conn:
            ids = [
                int(r["id"])
                for r in conn.execute(
                    "SELECT id FROM conversation_messages WHERE session_id = ? ORDER BY id ASC",
                    (sid,),
                ).fetchall()
            ]
            overflow = len(ids) - self.limit
            if overflow > 0:
                cut = ids[:overflow]
                conn.executemany("DELETE FROM conversation_messages WHERE id = ?", [(i,) for i in cut])
                conn.commit()

    def _trim_global(self) -> None:
        max_total = self.limit * 6
        with self._connect() as conn:
            total_row = conn.execute("SELECT COUNT(*) AS c FROM conversation_messages").fetchone()
            total = int(total_row["c"] or 0)
            if total <= max_total:
                return
            sessions = [
                str(r["session_id"] or "")
                for r in conn.execute("SELECT DISTINCT session_id FROM conversation_messages").fetchall()
            ]
            keep_ids: set[int] = set()
            for sid in sessions:
                rows = conn.execute(
                    """
                    SELECT id
                    FROM conversation_messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (sid, self.limit),
                ).fetchall()
                keep_ids.update(int(r["id"]) for r in rows)
            stale = [
                (int(r["id"]),)
                for r in conn.execute("SELECT id FROM conversation_messages").fetchall()
                if int(r["id"]) not in keep_ids
            ]
            if stale:
                conn.executemany("DELETE FROM conversation_messages WHERE id = ?", stale)
                conn.commit()

    def _snapshot_payload(self) -> dict:
        sessions: dict[str, list[dict]] = {}
        session_stats: dict[str, dict[str, int]] = {}
        with self._connect() as conn:
            session_rows = conn.execute("SELECT DISTINCT session_id FROM conversation_messages").fetchall()
        for row in session_rows:
            sid = self._normalize_session(row["session_id"])
            raw_rows = self._session_rows(sid)
            sessions[sid] = [self._compact_payload(item) for item in raw_rows]
            session_stats[sid] = {
                "message_count": len(raw_rows),
                "snapshot_count": len(sessions[sid]),
            }
        return {
            "version": 4,
            "backend": "sqlite+json_snapshot",
            "sessions": sessions,
            "session_stats": session_stats,
        }

    def _sync_json_snapshot(self) -> None:
        self.path.write_text(json.dumps(self._snapshot_payload(), ensure_ascii=False), encoding="utf-8")

    def load(self, limit: int | None = None, session_id: str | None = None) -> list[dict]:
        sid = self._normalize_session(session_id)
        rows = self._session_rows(sid)
        return rows[-(limit or self.limit):]

    def append(self, entry: dict, session_id: str | None = None) -> None:
        payload = dict(entry or {})
        sid = self._normalize_session(session_id or payload.get("session_id"))
        payload["session_id"] = sid
        role = str(payload.get("role") or "").strip() or "user"
        text = str(payload.get("text") or "")
        intent = str(payload.get("intent") or "")
        timestamp = str(payload.get("timestamp") or "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_messages (
                    session_id, role, text, intent, timestamp, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    role,
                    text,
                    intent,
                    timestamp,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()
        self._trim_session(sid)
        self._trim_global()
        self._sync_json_snapshot()

    def clear(self, session_id: str | None = None) -> None:
        with self._connect() as conn:
            if session_id is None:
                conn.execute("DELETE FROM conversation_messages")
            else:
                sid = self._normalize_session(session_id)
                conn.execute("DELETE FROM conversation_messages WHERE session_id = ?", (sid,))
            conn.commit()
        self._sync_json_snapshot()
