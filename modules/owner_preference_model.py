import json
import sqlite3
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("owner_preference_model", agent="owner_preference_model")


class OwnerPreferenceModel:
    """Owner Preference Model with explicit memory blocks and evidence-friendly signals."""

    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_tables()

    def _init_tables(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS owner_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pref_key TEXT UNIQUE NOT NULL,
                    value_json TEXT NOT NULL,
                    source TEXT DEFAULT 'owner',
                    confidence REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'active',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    last_observed_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS owner_preference_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pref_key TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    value_json TEXT DEFAULT '{}',
                    source TEXT DEFAULT 'system',
                    confidence_delta REAL DEFAULT 0.0,
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_owner_pref_key ON owner_preferences (pref_key);
                CREATE INDEX IF NOT EXISTS idx_owner_pref_events_key ON owner_preference_events (pref_key, created_at DESC);
            """)
            conn.commit()
        finally:
            conn.close()

    def set_preference(
        self,
        key: str,
        value: Any,
        source: str = "owner",
        confidence: float = 1.0,
        status: str = "active",
        notes: str = "",
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        confidence = _clamp_confidence(confidence)
        conn = sqlite3.connect(self.sqlite_path)
        try:
            prev = conn.execute(
                "SELECT value_json FROM owner_preferences WHERE pref_key = ?",
                (key,),
            ).fetchone()
            conn.execute(
                """INSERT INTO owner_preferences
                   (pref_key, value_json, source, confidence, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(pref_key) DO UPDATE SET
                     value_json = excluded.value_json,
                     source = excluded.source,
                     confidence = excluded.confidence,
                     status = excluded.status,
                     notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE owner_preferences.notes END,
                     updated_at = datetime('now'),
                     last_observed_at = datetime('now')""",
                (key, payload, source, confidence, status, notes),
            )
            conn.execute(
                """INSERT INTO owner_preference_events
                   (pref_key, signal_type, value_json, source, confidence_delta, notes)
                   VALUES (?, 'explicit', ?, ?, 0.0, ?)""",
                (key, payload, source, notes or "explicit_set"),
            )
            if prev and str(prev[0]) != payload:
                conn.execute(
                    """INSERT INTO owner_preference_events
                       (pref_key, signal_type, value_json, source, confidence_delta, notes)
                       VALUES (?, 'correction', ?, ?, 0.0, ?)""",
                    (key, payload, source, "explicit_override"),
                )
            conn.commit()
        finally:
            conn.close()
        # Best-effort semantic memory sync
        try:
            from memory.memory_manager import MemoryManager
            mm = MemoryManager()
            mm.store_knowledge(
                doc_id=f"owner_pref_{key}",
                text=f"owner preference: {key} = {value}",
                metadata={
                    "type": "owner_preference",
                    "key": key,
                    "source": source,
                    "force_save": True,
                    "policy_reason": "owner_explicit",
                },
            )
        except Exception:
            pass

    def get_preference(self, key: str) -> Optional[dict[str, Any]]:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM owner_preferences WHERE pref_key = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["value"] = _safe_json_loads(result.get("value_json", "{}"))
            return result
        finally:
            conn.close()

    def list_preferences(self, status: str = "active", limit: int = 200) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT * FROM owner_preferences
                   WHERE status = ?
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (status, limit),
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["value"] = _safe_json_loads(item.get("value_json", "{}"))
                results.append(item)
            return results
        finally:
            conn.close()

    def list_events(self, pref_key: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            if pref_key:
                rows = conn.execute(
                    """SELECT * FROM owner_preference_events
                       WHERE pref_key = ?
                       ORDER BY id DESC
                       LIMIT ?""",
                    (pref_key, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM owner_preference_events
                       ORDER BY id DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["value"] = _safe_json_loads(item.get("value_json", "{}"))
                results.append(item)
            return results
        finally:
            conn.close()

    def record_signal(
        self,
        key: str,
        value: Any,
        signal_type: str = "observation",
        source: str = "system",
        confidence_delta: float = 0.05,
        notes: str = "",
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """INSERT INTO owner_preference_events
                   (pref_key, signal_type, value_json, source, confidence_delta, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key, signal_type, payload, source, confidence_delta, notes),
            )
            row = conn.execute(
                "SELECT pref_key, confidence FROM owner_preferences WHERE pref_key = ?",
                (key,),
            ).fetchone()
            if row:
                new_conf = _clamp_confidence(float(row["confidence"]) + confidence_delta)
                conn.execute(
                    """UPDATE owner_preferences
                       SET confidence = ?, last_observed_at = datetime('now')
                       WHERE pref_key = ?""",
                    (new_conf, key),
                )
            else:
                seed_conf = _clamp_confidence(max(0.1, confidence_delta))
                conn.execute(
                    """INSERT INTO owner_preferences
                       (pref_key, value_json, source, confidence, status, notes)
                       VALUES (?, ?, ?, ?, 'active', ?)""",
                    (key, payload, source, seed_conf, notes),
                )
            conn.commit()
        finally:
            conn.close()

    def update_confidence(self, key: str, confidence: float) -> None:
        confidence = _clamp_confidence(confidence)
        conn = sqlite3.connect(self.sqlite_path)
        try:
            conn.execute(
                """UPDATE owner_preferences
                   SET confidence = ?, updated_at = datetime('now')
                   WHERE pref_key = ?""",
                (confidence, key),
            )
            conn.commit()
        finally:
            conn.close()

    def deactivate_preference(self, key: str, notes: str = "") -> None:
        conn = sqlite3.connect(self.sqlite_path)
        try:
            conn.execute(
                """UPDATE owner_preferences
                   SET status = 'inactive', updated_at = datetime('now'), notes = ?
                   WHERE pref_key = ?""",
                (notes[:200], key),
            )
            conn.execute(
                """INSERT INTO owner_preference_events
                   (pref_key, signal_type, value_json, source, confidence_delta, notes)
                   VALUES (?, 'deactivate', '{}', 'owner', 0.0, ?)""",
                (key, notes[:200]),
            )
            conn.commit()
        finally:
            conn.close()


def _safe_json_loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _clamp_confidence(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return float(value)
