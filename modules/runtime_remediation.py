"""Safe runtime remediation actions shared by dashboard and DecisionLoop."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings
from modules.model_profiles import ModelProfiles


SAFE_ACTIONS = {
    "apply_profile_economy",
    "disable_revenue_engine",
    "disable_tooling_live",
    "disable_discovery_intake",
    "enable_revenue_dry_run",
    "enable_guardrails_block",
    "tighten_self_healer_budget",
    "pause_self_learning_autopromote",
    "set_notify_minimal",
}


def _conn(sqlite_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(sqlite_path or settings.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_runtime_remediation_db(sqlite_path: str | None = None) -> None:
    conn = _conn(sqlite_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_remediation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_runtime_remediation_action_created
            ON runtime_remediation_events(action, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_runtime_remediation_outcome_created
            ON runtime_remediation_events(outcome, created_at DESC);
            """
        )
        conn.commit()
    finally:
        conn.close()


def plan_safe_action_updates(action: str) -> dict[str, Any]:
    act = str(action or "").strip().lower()
    if act == "apply_profile_economy":
        updates = ModelProfiles().profile_updates("economy") or {}
        if updates:
            updates["MODEL_ACTIVE_PROFILE"] = "economy"
        return updates
    if act == "disable_revenue_engine":
        return {"REVENUE_ENGINE_ENABLED": "false", "REVENUE_ENGINE_DRY_RUN": "true"}
    if act == "disable_tooling_live":
        return {"TOOLING_RUN_LIVE_ENABLED": "false"}
    if act == "disable_discovery_intake":
        return {"TOOLING_DISCOVERY_ENABLED": "false"}
    if act == "enable_revenue_dry_run":
        return {"REVENUE_ENGINE_DRY_RUN": "true"}
    if act == "enable_guardrails_block":
        return {"GUARDRAILS_BLOCK_ON_INJECTION": "true"}
    if act == "tighten_self_healer_budget":
        return {"SELF_HEALER_MAX_CHANGED_FILES": "5", "SELF_HEALER_MAX_CHANGED_LINES": "300"}
    if act == "pause_self_learning_autopromote":
        return {"SELF_LEARNING_AUTO_PROMOTE": "false"}
    if act == "set_notify_minimal":
        return {"NOTIFY_MODE": "minimal"}
    return {}


def apply_safe_action(action: str, env_path: str = "/home/vito/vito-agent/.env") -> dict[str, str]:
    act = str(action or "").strip().lower()
    if act not in SAFE_ACTIONS:
        return {}
    updates = {str(k): str(v) for k, v in (plan_safe_action_updates(act) or {}).items() if str(k)}
    if not updates:
        return {}
    text = ""
    try:
        p = Path(env_path)
        text = p.read_text() if p.exists() else ""
    except Exception:
        text = ""

    effective_updates: dict[str, str] = {}
    for k, v in updates.items():
        runtime_current = os.environ.get(k)
        if runtime_current is None and hasattr(settings, k):
            runtime_current = str(getattr(settings, k))
        file_match = re.search(rf"^{re.escape(k)}=(.*)$", text, flags=re.M)
        file_current = file_match.group(1).strip() if file_match else None
        runtime_ok = str(runtime_current) == str(v)
        file_ok = str(file_current) == str(v)
        if runtime_ok and file_ok:
            continue
        effective_updates[k] = v
    if not effective_updates:
        return {}
    for k, v in effective_updates.items():
        os.environ[k] = v
        if hasattr(settings, k):
            setattr(settings, k, v)
    try:
        p = Path(env_path)
        for k, v in effective_updates.items():
            if re.search(rf"^{k}=.*$", text, flags=re.M):
                text = re.sub(rf"^{k}=.*$", f"{k}={v}", text, flags=re.M)
            else:
                if text and not text.endswith("\n"):
                    text += "\n"
                text += f"{k}={v}\n"
        p.write_text(text)
    except Exception:
        pass
    return effective_updates


def record_safe_action_outcome(
    action: str,
    outcome: str,
    reason: str = "",
    sqlite_path: str | None = None,
) -> int:
    """Persist remediation outcomes for adaptive trust scoring."""
    act = str(action or "").strip().lower()
    out = str(outcome or "").strip().lower()
    if not act or not out:
        return 0
    _init_runtime_remediation_db(sqlite_path)
    conn = _conn(sqlite_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO runtime_remediation_events (action, outcome, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                act[:120],
                out[:40],
                str(reason or "")[:300],
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def get_safe_action_trust(action: str, days: int = 30, sqlite_path: str | None = None) -> dict[str, Any]:
    """Compute lightweight trust metrics for a remediation action."""
    act = str(action or "").strip().lower()
    if not act:
        return {"action": "", "total": 0, "applied": 0, "failed": 0, "noop": 0, "success_rate": 0.0, "bias": 0.0}
    _init_runtime_remediation_db(sqlite_path)
    conn = _conn(sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN outcome = 'applied' THEN 1 ELSE 0 END) AS applied,
              SUM(CASE WHEN outcome = 'failed' THEN 1 ELSE 0 END) AS failed,
              SUM(CASE WHEN outcome = 'noop' THEN 1 ELSE 0 END) AS noop
            FROM runtime_remediation_events
            WHERE action = ?
              AND created_at >= datetime('now', ?)
            """,
            (act, f"-{max(1, int(days or 30))} day"),
        ).fetchone()
        total = int((row["total"] if row else 0) or 0)
        applied = int((row["applied"] if row else 0) or 0)
        failed = int((row["failed"] if row else 0) or 0)
        noop = int((row["noop"] if row else 0) or 0)
        success_rate = (float(applied) / float(total)) if total > 0 else 0.0
        # Keep effect bounded so policy signals remain primary.
        bias = 0.0
        if total >= 3:
            bias = max(-1.5, min(1.5, (success_rate - 0.5) * 3.0 - (float(failed) / float(total))))
        return {
            "action": act,
            "total": total,
            "applied": applied,
            "failed": failed,
            "noop": noop,
            "success_rate": round(success_rate, 4),
            "bias": round(bias, 4),
        }
    finally:
        conn.close()


def rank_safe_action_suggestions(
    suggestions: list[dict[str, Any]],
    sqlite_path: str | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Rank remediation suggestions by policy score + historical trust."""
    ranked: list[dict[str, Any]] = []
    for item in list(suggestions or []):
        rec = dict(item or {})
        action = str(rec.get("action") or "").strip().lower()
        trust = get_safe_action_trust(action=action, days=days, sqlite_path=sqlite_path) if action else {}
        base_score = float(rec.get("score", 0) or 0.0)
        bias = float((trust or {}).get("bias", 0.0) or 0.0)
        rec["trust"] = trust
        rec["effective_score"] = round(base_score + bias, 4)
        ranked.append(rec)
    return sorted(
        ranked,
        key=lambda r: (
            -float(r.get("effective_score", r.get("score", 0)) or 0),
            int(r.get("priority", 9) or 9),
            str(r.get("action", "")),
        ),
    )
