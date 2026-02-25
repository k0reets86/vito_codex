"""LLM evaluation and cost-anomaly summaries for operator observability."""

from __future__ import annotations

import sqlite3
from typing import Optional

from config.settings import settings


class LLMEvals:
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
                CREATE TABLE IF NOT EXISTS spend_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd REAL NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS data_lake_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_json TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS llm_guardrail_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    task_type TEXT DEFAULT '',
                    severity TEXT DEFAULT 'warn',
                    blocked INTEGER DEFAULT 0,
                    snippet TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS llm_eval_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    score REAL DEFAULT 0,
                    fail_rate REAL DEFAULT 0,
                    blocked_count INTEGER DEFAULT 0,
                    daily_cost REAL DEFAULT 0,
                    baseline_cost REAL DEFAULT 0,
                    anomaly INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def compute(self) -> dict:
        conn = self._get_conn()
        try:
            day_cost = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) s FROM spend_log WHERE date = date('now')"
            ).fetchone()
            baseline = conn.execute(
                """
                SELECT COALESCE(AVG(day_sum), 0) a FROM (
                  SELECT date, SUM(cost_usd) day_sum
                  FROM spend_log
                  WHERE date >= date('now', '-7 day') AND date < date('now')
                  GROUP BY date
                )
                """
            ).fetchone()
            calls = conn.execute(
                """
                SELECT
                  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) ok,
                  SUM(CASE WHEN status = 'success' THEN 0 ELSE 1 END) bad,
                  COUNT(*) total
                FROM data_lake_events
                WHERE agent = 'llm_router'
                  AND task_type LIKE 'llm:%'
                  AND created_at >= datetime('now', '-1 day')
                """
            ).fetchone()
            blocked = conn.execute(
                """
                SELECT COUNT(*) n
                FROM llm_guardrail_events
                WHERE blocked = 1
                  AND created_at >= datetime('now', '-1 day')
                """
            ).fetchone()
            daily_cost = float((day_cost["s"] if day_cost else 0.0) or 0.0)
            baseline_cost = float((baseline["a"] if baseline else 0.0) or 0.0)
            total = int((calls["total"] if calls else 0) or 0)
            bad = int((calls["bad"] if calls else 0) or 0)
            fail_rate = (float(bad) / float(total)) if total > 0 else 0.0
            blocked_count = int((blocked["n"] if blocked else 0) or 0)
            anomaly = bool(baseline_cost > 0 and daily_cost > baseline_cost * 2.0 and daily_cost >= 1.0)

            score = 10.0
            score -= min(4.0, fail_rate * 10.0)
            score -= min(2.0, blocked_count * 0.2)
            if anomaly:
                score -= 2.0
            score = max(0.0, round(score, 2))

            notes = []
            if anomaly:
                notes.append("cost_anomaly")
            if fail_rate > 0.2:
                notes.append("high_fail_rate")
            if blocked_count > 0:
                notes.append("guardrails_blocks")

            conn.execute(
                """
                INSERT INTO llm_eval_runs
                (score, fail_rate, blocked_count, daily_cost, baseline_cost, anomaly, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score,
                    fail_rate,
                    blocked_count,
                    daily_cost,
                    baseline_cost,
                    1 if anomaly else 0,
                    ",".join(notes)[:500],
                ),
            )
            conn.commit()
            return {
                "score": score,
                "fail_rate": round(fail_rate, 4),
                "blocked_count_24h": blocked_count,
                "daily_cost_usd": round(daily_cost, 6),
                "baseline_cost_usd": round(baseline_cost, 6),
                "cost_anomaly": anomaly,
                "notes": notes,
            }
        finally:
            conn.close()

    def recent_runs(self, limit: int = 30) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT score, fail_rate, blocked_count, daily_cost, baseline_cost, anomaly, notes, created_at
                FROM llm_eval_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
