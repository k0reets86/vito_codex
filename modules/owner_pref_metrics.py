import sqlite3
from typing import Optional

from config.settings import settings


class OwnerPreferenceMetrics:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def summary(self) -> dict:
        conn = self._conn()
        try:
            prefs = conn.execute("SELECT COUNT(*) n FROM owner_preferences WHERE status='active'").fetchone()
            sets = conn.execute(
                "SELECT COUNT(*) n FROM data_lake_events WHERE task_type='owner_preference_set'"
            ).fetchone()
            uses = conn.execute(
                "SELECT COUNT(*) n FROM data_lake_events WHERE task_type='owner_prefs_used'"
            ).fetchone()
            deacts = conn.execute(
                "SELECT COUNT(*) n FROM owner_preference_events WHERE signal_type='deactivate'"
            ).fetchone()
            auto = conn.execute(
                "SELECT COUNT(*) n FROM owner_preference_events WHERE notes='auto_detect'"
            ).fetchone()
            explicit = conn.execute(
                "SELECT COUNT(*) n FROM owner_preference_events WHERE signal_type='explicit'"
            ).fetchone()
            corrections = conn.execute(
                "SELECT COUNT(*) n FROM owner_preference_events WHERE signal_type='correction'"
            ).fetchone()
            last = conn.execute(
                "SELECT MAX(updated_at) ts FROM owner_preferences"
            ).fetchone()
            return {
                "active_prefs": int(prefs[0] or 0),
                "set_events": int(sets[0] or 0),
                "use_events": int(uses[0] or 0),
                "deactivate_events": int(deacts[0] or 0),
                "auto_detect_events": int(auto[0] or 0),
                "explicit_events": int(explicit[0] or 0),
                "correction_events": int(corrections[0] or 0),
                "last_updated": last[0] or "",
            }
        except Exception:
            return {"active_prefs": 0, "set_events": 0, "use_events": 0, "deactivate_events": 0, "last_updated": ""}
        finally:
            conn.close()
