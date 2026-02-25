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
            # Forward-compatible columns for normalized analytics
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(data_lake_events)").fetchall()}
            if "goal_id" not in cols:
                conn.execute("ALTER TABLE data_lake_events ADD COLUMN goal_id TEXT DEFAULT ''")
            if "trace_id" not in cols:
                conn.execute("ALTER TABLE data_lake_events ADD COLUMN trace_id TEXT DEFAULT ''")
            if "latency_ms" not in cols:
                conn.execute("ALTER TABLE data_lake_events ADD COLUMN latency_ms INTEGER DEFAULT 0")
            if "cost_usd" not in cols:
                conn.execute("ALTER TABLE data_lake_events ADD COLUMN cost_usd REAL DEFAULT 0")
            if "severity" not in cols:
                conn.execute("ALTER TABLE data_lake_events ADD COLUMN severity TEXT DEFAULT 'info'")
            if "source" not in cols:
                conn.execute("ALTER TABLE data_lake_events ADD COLUMN source TEXT DEFAULT ''")
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

    def record(
        self,
        agent: str,
        task_type: str,
        status: str,
        output=None,
        error: str = "",
        goal_id: str = "",
        trace_id: str = "",
        latency_ms: int = 0,
        cost_usd: float = 0.0,
        severity: str = "info",
        source: str = "",
    ) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO data_lake_events
                (agent, task_type, status, output_json, error, goal_id, trace_id, latency_ms, cost_usd, severity, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent,
                    task_type,
                    status,
                    json.dumps(output, ensure_ascii=False)[:4000] if output is not None else "",
                    (error or "")[:500],
                    goal_id[:100],
                    trace_id[:100],
                    int(latency_ms or 0),
                    float(cost_usd or 0.0),
                    (severity or "info")[:20],
                    source[:100],
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

    def record_handoff(
        self,
        from_agent: str,
        to_agent: str,
        capability: str,
        step: str,
        status: str = "success",
        goal_id: str = "",
        trace_id: str = "",
    ) -> None:
        """Structured handoff trace event for multi-agent orchestration."""
        self.record(
            agent=from_agent,
            task_type="handoff",
            status=status,
            output={
                "from": from_agent,
                "to": to_agent,
                "capability": capability,
                "step": (step or "")[:220],
            },
            goal_id=goal_id,
            trace_id=trace_id,
            source="handoff_trace",
        )

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
                {
                    "agent": r[0],
                    "ok": r[1],
                    "fail": r[2],
                    "total": r[3],
                    "success_rate": round((float(r[1]) / float(r[3])) if r[3] else 0.0, 4),
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

    def kpi_summary(self, days: int = 30) -> dict:
        """Top-level KPI summary for dashboard/owner report."""
        out = {
            "window_days": int(days),
            "events_total": 0,
            "events_success": 0,
            "events_failed": 0,
            "success_rate": 0.0,
            "active_agents": 0,
            "agent_top": [],
        }
        try:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as ok,
                  SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as fail
                FROM data_lake_events
                WHERE created_at >= datetime('now', ?)
                """,
                (f"-{int(days)} day",),
            ).fetchone()
            total = int(row[0] or 0)
            ok = int(row[1] or 0)
            fail = int(row[2] or 0)
            out["events_total"] = total
            out["events_success"] = ok
            out["events_failed"] = fail
            out["success_rate"] = round((ok / total) if total else 0.0, 4)

            top = self.agent_stats(days=days)
            out["active_agents"] = len(top)
            out["agent_top"] = top[:10]
            return out
        except Exception:
            return out
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def recent_handoffs(self, limit: int = 100) -> list[dict]:
        """Recent handoff trace events (parsed lightweight output)."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT id, agent, status, output_json, goal_id, trace_id, created_at
                FROM data_lake_events
                WHERE task_type = 'handoff'
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            out = []
            for r in rows:
                payload = {}
                try:
                    payload = json.loads(r["output_json"] or "{}")
                except Exception:
                    payload = {}
                out.append(
                    {
                        "id": r["id"],
                        "agent": r["agent"],
                        "status": r["status"],
                        "from": payload.get("from", r["agent"]),
                        "to": payload.get("to", ""),
                        "capability": payload.get("capability", ""),
                        "step": payload.get("step", ""),
                        "goal_id": r["goal_id"] or "",
                        "trace_id": r["trace_id"] or "",
                        "created_at": r["created_at"],
                    }
                )
            return out
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def handoff_summary(self, days: int = 7) -> list[dict]:
        """Aggregate handoff success/fail by from->to pair."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT output_json, status
                FROM data_lake_events
                WHERE task_type='handoff'
                  AND created_at >= datetime('now', ?)
                """,
                (f"-{int(days)} day",),
            ).fetchall()
            agg: dict[tuple[str, str], dict] = {}
            for r in rows:
                try:
                    p = json.loads(r["output_json"] or "{}")
                except Exception:
                    p = {}
                f = str(p.get("from", "") or "")
                t = str(p.get("to", "") or "")
                if not f and not t:
                    continue
                k = (f, t)
                cur = agg.setdefault(k, {"from": f, "to": t, "ok": 0, "fail": 0, "total": 0})
                cur["total"] += 1
                if str(r["status"] or "").lower() in {"success", "completed", "ok"}:
                    cur["ok"] += 1
                else:
                    cur["fail"] += 1
            return sorted(agg.values(), key=lambda x: x["total"], reverse=True)
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

    def kpi_daily(self, days: int = 30) -> list[dict]:
        """Daily KPI trend for dashboard charts/tables."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT date(created_at) as d,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as ok,
                       SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as fail,
                       COUNT(*) as total,
                       AVG(latency_ms) as avg_latency,
                       SUM(cost_usd) as total_cost
                FROM data_lake_events
                WHERE created_at >= datetime('now', ?)
                GROUP BY date(created_at)
                ORDER BY d DESC
                """,
                (f"-{int(days)} day",),
            ).fetchall()
            out = []
            for r in rows:
                total = int(r[3] or 0)
                ok = int(r[1] or 0)
                out.append(
                    {
                        "date": r[0],
                        "ok": ok,
                        "fail": int(r[2] or 0),
                        "total": total,
                        "avg_latency_ms": int(r[4] or 0),
                        "cost_usd": float(r[5] or 0.0),
                        "success_rate": round((ok / total) if total else 0.0, 4),
                    }
                )
            return out
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass
