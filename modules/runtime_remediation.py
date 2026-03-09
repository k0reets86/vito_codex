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

REMEDIATION_OUTCOMES = {
    "candidate",
    "verified",
    "promoted",
    "applied",
    "failed",
    "noop",
    "held",
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
                source_agent TEXT DEFAULT '',
                task_family TEXT DEFAULT '',
                source TEXT DEFAULT '',
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
    source_agent: str = "",
    task_family: str = "",
    source: str = "runtime",
    sqlite_path: str | None = None,
) -> int:
    """Persist remediation outcomes for adaptive trust scoring."""
    act = str(action or "").strip().lower()
    out = str(outcome or "").strip().lower()
    if not act or not out:
        return 0
    if out not in REMEDIATION_OUTCOMES:
        out = "failed"
    _init_runtime_remediation_db(sqlite_path)
    conn = _conn(sqlite_path)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(runtime_remediation_events)").fetchall()}
        if "source_agent" not in cols:
            conn.execute("ALTER TABLE runtime_remediation_events ADD COLUMN source_agent TEXT DEFAULT ''")
        if "task_family" not in cols:
            conn.execute("ALTER TABLE runtime_remediation_events ADD COLUMN task_family TEXT DEFAULT ''")
        if "source" not in cols:
            conn.execute("ALTER TABLE runtime_remediation_events ADD COLUMN source TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    try:
        cur = conn.execute(
            """
            INSERT INTO runtime_remediation_events (action, outcome, source_agent, task_family, source, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                act[:120],
                out[:40],
                str(source_agent or "")[:80],
                str(task_family or "")[:80],
                str(source or "runtime")[:80],
                str(reason or "")[:300],
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def record_remediation_candidate(
    action: str,
    *,
    reason: str = "",
    source_agent: str = "",
    task_family: str = "",
    source: str = "self_healer",
    sqlite_path: str | None = None,
) -> int:
    return record_safe_action_outcome(
        action=action,
        outcome="candidate",
        reason=reason,
        source_agent=source_agent,
        task_family=task_family,
        source=source,
        sqlite_path=sqlite_path,
    )


def record_remediation_verification(
    action: str,
    *,
    verified: bool,
    reason: str = "",
    source_agent: str = "",
    task_family: str = "",
    source: str = "self_healer_verify",
    sqlite_path: str | None = None,
) -> int:
    return record_safe_action_outcome(
        action=action,
        outcome="verified" if verified else "held",
        reason=reason,
        source_agent=source_agent,
        task_family=task_family,
        source=source,
        sqlite_path=sqlite_path,
    )


def record_remediation_promotion(
    action: str,
    *,
    promoted: bool,
    reason: str = "",
    source_agent: str = "",
    task_family: str = "",
    source: str = "self_healer_apply",
    sqlite_path: str | None = None,
) -> int:
    return record_safe_action_outcome(
        action=action,
        outcome="promoted" if promoted else "failed",
        reason=reason,
        source_agent=source_agent,
        task_family=task_family,
        source=source,
        sqlite_path=sqlite_path,
    )


def suggest_safe_actions_for_failure(
    *,
    agent: str,
    error_type: str = "",
    message: str = "",
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ctx = context or {}
    agent_name = str(agent or "").strip().lower()
    err_type = str(error_type or "").strip().lower()
    msg = str(message or "").strip().lower()
    hay = " ".join(
        [
            agent_name,
            err_type,
            msg,
            str(ctx.get("task_type", "") or ""),
            str(ctx.get("task_family", "") or ""),
            str(ctx.get("step", "") or ""),
        ]
    ).lower()
    candidates: list[dict[str, Any]] = []

    def _push(action: str, score: float, reason: str, priority: int = 5) -> None:
        if action not in SAFE_ACTIONS:
            return
        candidates.append(
            {
                "action": action,
                "score": float(score),
                "priority": int(priority),
                "reason": reason[:220],
                "source_agent": agent_name,
                "task_family": str(ctx.get("task_family", "") or "")[:80],
            }
        )

    if any(x in hay for x in ("prompt injection", "injection", "unsafe prompt", "jailbreak")):
        _push("enable_guardrails_block", 9.5, "Detected injection/safety-style failure", 1)
    if any(x in hay for x in ("429", "rate limit", "quota", "budget", "cost anomaly", "provider")):
        _push("apply_profile_economy", 8.8, "Provider/rate-limit pressure detected", 1)
        _push("set_notify_minimal", 7.1, "Reduce noise during degraded provider period", 4)
    if any(x in hay for x in ("tooling", "openapi", "mcp", "adapter", "contract mismatch", "signature")):
        _push("disable_tooling_live", 8.9, "Tooling/live adapter instability detected", 1)
        _push("disable_discovery_intake", 7.9, "Freeze discovery while tooling issues are active", 3)
    if any(x in hay for x in ("self_learning", "auto_promote", "candidate", "flaky", "promotion")):
        _push("pause_self_learning_autopromote", 9.0, "Self-learning instability detected", 1)
    if any(x in hay for x in ("self_healer", "autofix", "rollback", "patch budget", "change budget")):
        _push("tighten_self_healer_budget", 8.7, "Self-healer should reduce mutation blast radius", 1)
    if any(x in hay for x in ("revenue", "publish", "commerce", "payment", "listing")):
        _push("enable_revenue_dry_run", 7.8, "Commerce flow degraded; keep dry-run safety", 3)
    if "revenue_engine" in hay:
        _push("disable_revenue_engine", 8.2, "Revenue engine explicitly implicated by failure", 2)

    dedup: dict[str, dict[str, Any]] = {}
    for item in candidates:
        key = str(item.get("action") or "").strip().lower()
        prev = dedup.get(key)
        if prev is None or float(item.get("score", 0.0)) > float(prev.get("score", 0.0)):
            dedup[key] = item
    return rank_safe_action_suggestions(list(dedup.values()))


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
