"""DataLake — minimal event store for tasks/results."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("data_lake", agent="data_lake")


class DataLake:
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
                CREATE TABLE IF NOT EXISTS data_lake_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_json TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS data_lake_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    rationale TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS data_lake_budget (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"DataLake init failed: {e}", extra={"event": "db_init_error"})

    def record(self, agent: str, task_type: str, status: str, output=None, error: str = "") -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO data_lake_events (agent, task_type, status, output_json, error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    agent,
                    task_type,
                    status,
                    json.dumps(output, ensure_ascii=False)[:4000] if output is not None else "",
                    (error or "")[:500],
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"DataLake record failed: {e}", extra={"event": "record_error"})
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def record_decision(self, actor: str, decision: str, rationale: str = "") -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO data_lake_decisions (actor, decision, rationale)
                VALUES (?, ?, ?)
                """,
                (actor[:100], decision[:500], rationale[:2000]),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def record_budget(self, agent: str, amount: float, category: str = "", description: str = "") -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO data_lake_budget (agent, amount, category, description)
                VALUES (?, ?, ?, ?)
                """,
                (agent[:100], float(amount), category[:100], description[:500]),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def budget_stats(self, days: int = 30) -> list[dict]:
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT agent, SUM(amount) as total
                FROM data_lake_budget
                WHERE created_at >= datetime('now', ?)
                GROUP BY agent
                ORDER BY total DESC
                """,
                (f"-{int(days)} day",),
            ).fetchall()
            return [{"agent": r[0], "total": r[1]} for r in rows]
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def decision_stats(self, limit: int = 50) -> list[dict]:
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT actor, decision, rationale, created_at
                FROM data_lake_decisions
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {"actor": r[0], "decision": r[1], "rationale": r[2], "created_at": r[3]}
                for r in rows
            ]
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass
    def agent_stats(self, days: int = 30) -> list[dict]:
        """Aggregate success/fail counts per agent over recent days."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT agent,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as ok,
                       SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as fail,
                       COUNT(*) as total
                FROM data_lake_events
                WHERE created_at >= datetime('now', ?)
                GROUP BY agent
                ORDER BY total DESC
                """,
                (f"-{int(days)} day",),
            ).fetchall()
            return [
                {"agent": r[0], "ok": r[1], "fail": r[2], "total": r[3]}
                for r in rows
            ]
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def recent_events(self, limit: int = 50) -> list[dict]:
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT id, agent, task_type, status, substr(output_json,1,500), error, created_at
                FROM data_lake_events
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "agent": r[1],
                    "task_type": r[2],
                    "status": r[3],
                    "output": r[4],
                    "error": r[5],
                    "created_at": r[6],
                }
                for r in rows
            ]
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass
