"""Operator policies for tool allowlist and per-capability daily budgets."""

from __future__ import annotations

import sqlite3
from typing import Optional

from config.settings import settings


class OperatorPolicy:
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
                CREATE TABLE IF NOT EXISTS operator_tool_policy (
                    tool_key TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    notes TEXT DEFAULT '',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS operator_budget_policy (
                    actor_key TEXT PRIMARY KEY,
                    daily_limit_usd REAL DEFAULT 0,
                    hard_block INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS data_lake_budget (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS data_lake_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    task_type TEXT DEFAULT '',
                    status TEXT DEFAULT '',
                    output_json TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    goal_id TEXT DEFAULT '',
                    trace_id TEXT DEFAULT '',
                    latency_ms INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    severity TEXT DEFAULT 'info',
                    source TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def set_tool_policy(self, tool_key: str, enabled: bool, notes: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO operator_tool_policy (tool_key, enabled, notes, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(tool_key) DO UPDATE SET
                  enabled = excluded.enabled,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (tool_key[:120], 1 if enabled else 0, notes[:500]),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_tool_policy(self, tool_key: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM operator_tool_policy WHERE tool_key = ?", (tool_key,))
            conn.commit()
        finally:
            conn.close()

    def is_tool_allowed(self, tool_key: str) -> tuple[bool, str]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT enabled, notes FROM operator_tool_policy WHERE tool_key = ?",
                (tool_key,),
            ).fetchone()
            if not row:
                return True, "default_allow"
            if int(row["enabled"] or 0) == 1:
                return True, "operator_allow"
            return False, (row["notes"] or "operator_block")
        finally:
            conn.close()

    def list_tool_policies(self, limit: int = 200) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT tool_key, enabled, notes, updated_at
                FROM operator_tool_policy
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def set_budget_policy(self, actor_key: str, daily_limit_usd: float, hard_block: bool = False, notes: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO operator_budget_policy (actor_key, daily_limit_usd, hard_block, notes, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(actor_key) DO UPDATE SET
                  daily_limit_usd = excluded.daily_limit_usd,
                  hard_block = excluded.hard_block,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (actor_key[:120], float(max(daily_limit_usd, 0.0)), 1 if hard_block else 0, notes[:500]),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_budget_policy(self, actor_key: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM operator_budget_policy WHERE actor_key = ?", (actor_key,))
            conn.commit()
        finally:
            conn.close()

    def list_budget_policies(self, limit: int = 200) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT actor_key, daily_limit_usd, hard_block, notes, updated_at
                FROM operator_budget_policy
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def check_actor_budget(self, actor_key: str) -> dict:
        conn = self._get_conn()
        try:
            policy = conn.execute(
                "SELECT daily_limit_usd, hard_block, notes FROM operator_budget_policy WHERE actor_key = ?",
                (actor_key,),
            ).fetchone()
            if not policy:
                return {"allowed": True, "reason": "no_budget_policy", "spent_usd": 0.0, "limit_usd": 0.0}
            limit_usd = float(policy["daily_limit_usd"] or 0.0)
            if limit_usd <= 0:
                return {"allowed": True, "reason": "limit_disabled", "spent_usd": 0.0, "limit_usd": 0.0}

            spent_1 = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) s
                FROM data_lake_budget
                WHERE agent = ?
                  AND created_at >= datetime('now', '-1 day')
                """,
                (actor_key,),
            ).fetchone()
            spent_2 = conn.execute(
                """
                SELECT COALESCE(SUM(cost_usd), 0) s
                FROM data_lake_events
                WHERE agent = ?
                  AND created_at >= datetime('now', '-1 day')
                """,
                (actor_key,),
            ).fetchone()
            spent = float((spent_1["s"] if spent_1 else 0.0) or 0.0) + float((spent_2["s"] if spent_2 else 0.0) or 0.0)
            hard_block = int(policy["hard_block"] or 0) == 1
            if spent > limit_usd and hard_block:
                return {
                    "allowed": False,
                    "reason": f"operator_budget_block:{policy['notes'] or 'limit exceeded'}",
                    "spent_usd": spent,
                    "limit_usd": limit_usd,
                }
            if spent > limit_usd:
                return {
                    "allowed": True,
                    "reason": f"operator_budget_soft:{policy['notes'] or 'limit exceeded'}",
                    "spent_usd": spent,
                    "limit_usd": limit_usd,
                }
            return {"allowed": True, "reason": "within_operator_budget", "spent_usd": spent, "limit_usd": limit_usd}
        finally:
            conn.close()
