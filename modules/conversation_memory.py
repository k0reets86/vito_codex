from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable
from config.paths import root_path


class ConversationMemory:
    def __init__(self, path: Path | str | None = None, limit: int = 50) -> None:
        self.path = Path(path or root_path("runtime", "conversation_history.json"))
        self.limit = limit
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"version": 2, "sessions": {}}, ensure_ascii=False), encoding="utf-8")

    def _load_all(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                rows: list[dict] = []
                sessions = data.get("sessions") or {}
                if isinstance(sessions, dict):
                    for session_id, items in sessions.items():
                        if not isinstance(items, list):
                            continue
                        for row in items:
                            if isinstance(row, dict):
                                payload = dict(row)
                                payload["session_id"] = self._normalize_session(payload.get("session_id") or session_id)
                                rows.append(payload)
                return rows
        except Exception:
            pass
        return []

    def _dump_all(self, rows: list[dict]) -> None:
        sessions: dict[str, list[dict]] = {}
        for row in rows:
            payload = dict(row)
            sid = self._normalize_session(payload.get("session_id"))
            payload["session_id"] = sid
            sessions.setdefault(sid, []).append(payload)
        self.path.write_text(
            json.dumps({"version": 2, "sessions": sessions}, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_session(session_id: str | None) -> str:
        sid = str(session_id or "default").strip()
        return sid or "default"

    def load(self, limit: int | None = None, session_id: str | None = None) -> list[dict]:
        sid = self._normalize_session(session_id)
        data = [
            row for row in self._load_all()
            if self._normalize_session(row.get("session_id")) == sid
        ]
        return data[-(limit or self.limit):]

    def append(self, entry: dict, session_id: str | None = None) -> None:
        data = self._load_all()
        sid = self._normalize_session(session_id or entry.get("session_id"))
        payload = dict(entry)
        payload["session_id"] = sid
        data.append(payload)
        # Always enforce per-session limit for current session.
        same_idx = [i for i, row in enumerate(data) if self._normalize_session(row.get("session_id")) == sid]
        overflow = len(same_idx) - self.limit
        if overflow > 0:
            drop = set(same_idx[:overflow])
            data = [row for i, row in enumerate(data) if i not in drop]
        # Keep bounded history per session while preserving cross-session data.
        if len(data) > self.limit * 6:
            kept: list[dict] = []
            counters: dict[str, int] = {}
            for row in reversed(data):
                row_sid = self._normalize_session(row.get("session_id"))
                cnt = counters.get(row_sid, 0)
                if cnt >= self.limit:
                    continue
                counters[row_sid] = cnt + 1
                kept.append(row)
            data = list(reversed(kept))
        self._dump_all(data)

    def clear(self, session_id: str | None = None) -> None:
        if session_id is None:
            self._dump_all([])
            return
        sid = self._normalize_session(session_id)
        data = [
            row for row in self._load_all()
            if self._normalize_session(row.get("session_id")) != sid
        ]
        self._dump_all(data)
