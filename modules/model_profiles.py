"""Model profile presets for safe operator switching."""

from __future__ import annotations

import sqlite3
from typing import Optional

from config.settings import settings


class ModelProfiles:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS model_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT UNIQUE NOT NULL,
                    default_model TEXT DEFAULT '',
                    enabled_models TEXT DEFAULT '',
                    disabled_models TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            row = conn.execute("SELECT COUNT(*) AS n FROM model_profiles").fetchone()
            if int((row["n"] if row else 0) or 0) == 0:
                conn.execute(
                    """
                    INSERT INTO model_profiles
                    (profile_name, default_model, enabled_models, disabled_models, notes)
                    VALUES
                    ('balanced', '', '', '', 'Default balanced profile'),
                    ('economy', '', '', 'anthropic/claude-opus-4-1,openai/gpt-5', 'Cost-focused profile'),
                    ('quality', '', 'anthropic/claude-opus-4-1,openai/gpt-5', '', 'High quality profile')
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def list_profiles(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM model_profiles
                ORDER BY profile_name ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_profile(self, profile_name: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM model_profiles WHERE profile_name = ?",
                (str(profile_name or "").strip(),),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def save_profile(
        self,
        profile_name: str,
        default_model: str = "",
        enabled_models: str = "",
        disabled_models: str = "",
        notes: str = "",
    ) -> dict:
        name = str(profile_name or "").strip().lower()
        if not name:
            return {"ok": False, "error": "profile_name_required"}
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO model_profiles
                (profile_name, default_model, enabled_models, disabled_models, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(profile_name) DO UPDATE SET
                  default_model = excluded.default_model,
                  enabled_models = excluded.enabled_models,
                  disabled_models = excluded.disabled_models,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (
                    name[:80],
                    str(default_model or "")[:160],
                    str(enabled_models or "")[:4000],
                    str(disabled_models or "")[:4000],
                    str(notes or "")[:1000],
                ),
            )
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    def delete_profile(self, profile_name: str) -> bool:
        name = str(profile_name or "").strip().lower()
        if name in {"balanced", "economy", "quality"}:
            return False
        conn = self._get_conn()
        try:
            cur = conn.execute("DELETE FROM model_profiles WHERE profile_name = ?", (name,))
            conn.commit()
            return int(cur.rowcount or 0) > 0
        finally:
            conn.close()

    def profile_updates(self, profile_name: str) -> dict:
        row = self.get_profile(profile_name)
        if not row:
            return {}
        updates = {}
        if row.get("default_model"):
            updates["OPENROUTER_DEFAULT_MODEL"] = str(row.get("default_model") or "")
        updates["LLM_ENABLED_MODELS"] = str(row.get("enabled_models") or "")
        updates["LLM_DISABLED_MODELS"] = str(row.get("disabled_models") or "")
        return updates
