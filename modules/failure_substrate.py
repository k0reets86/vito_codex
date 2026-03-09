"""Unified failure substrate for runtime routing.

Consolidates failure memory, negative execution facts and weak playbooks into
one ranked anti-pattern/control surface that agents can actually use.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from modules.execution_facts import ExecutionFacts
from modules.failure_memory import FailureMemory
from modules.playbook_registry import PlaybookRegistry


def _parse_dt(value: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc)
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _age_hours(value: str) -> float:
    dt = _parse_dt(value)
    delta = datetime.now(timezone.utc) - dt
    return max(0.0, delta.total_seconds() / 3600.0)


def _risk_from_age(age_hours: float) -> float:
    if age_hours <= 24:
        return 1.0
    if age_hours <= 72:
        return 0.88
    if age_hours <= 168:
        return 0.74
    if age_hours <= 336:
        return 0.62
    return 0.48


def _normalize_task(text: str) -> str:
    return str(text or "").strip().lower()


def build_failure_substrate(
    *,
    agent: str,
    task_type: str = "",
    limit: int = 10,
    sqlite_path: Optional[str] = None,
) -> dict[str, Any]:
    agent_low = str(agent or "").strip().lower()
    task_low = _normalize_task(task_type)
    entries: list[dict[str, Any]] = []

    try:
        failures = FailureMemory(sqlite_path=sqlite_path).recent(limit=max(limit * 5, 25))
    except Exception:
        failures = []
    for row in failures:
        row_agent = str(row.get("agent") or "").strip().lower()
        row_task = _normalize_task(str(row.get("task_type") or ""))
        if row_agent != agent_low:
            continue
        if task_low and row_task and row_task != task_low:
            continue
        age_h = _age_hours(str(row.get("created_at") or ""))
        base = 0.88 if row_task == task_low and task_low else 0.76
        entries.append(
            {
                "kind": "failure_memory",
                "summary": str(row.get("detail") or row.get("error") or "").strip()[:300],
                "error": str(row.get("error") or "").strip()[:300],
                "task_type": row_task,
                "created_at": str(row.get("created_at") or ""),
                "risk_score": round(base * _risk_from_age(age_h), 4),
                "avoid_action": "",
                "source": "failure_memory",
            }
        )

    try:
        facts = ExecutionFacts(sqlite_path=sqlite_path).recent_facts(limit=max(limit * 8, 60))
    except Exception:
        facts = []
    for fact in facts:
        action = str(getattr(fact, "action", "") or "")
        status = str(getattr(fact, "status", "") or "").strip().lower()
        if not action.startswith(f"{agent_low}:"):
            continue
        if status in {"success", "completed", "published", "done", "ok"}:
            continue
        fact_task = _normalize_task(action.split(":", 1)[-1] if ":" in action else action)
        if task_low and task_low not in fact_task:
            continue
        age_h = _age_hours(str(getattr(fact, "created_at", "") or ""))
        entries.append(
            {
                "kind": "execution_fact",
                "summary": str(getattr(fact, "detail", "") or "").strip()[:300],
                "error": status,
                "task_type": fact_task,
                "created_at": str(getattr(fact, "created_at", "") or ""),
                "risk_score": round(0.82 * _risk_from_age(age_h), 4),
                "avoid_action": action,
                "source": "execution_facts",
            }
        )

    try:
        playbooks = PlaybookRegistry(sqlite_path=sqlite_path).find(agent=agent_low, task_type=task_low, limit=max(limit * 3, 15))
    except Exception:
        playbooks = []
    for row in playbooks:
        succ = int(row.get("success_count") or 0)
        fail = int(row.get("fail_count") or 0)
        total = succ + fail
        if fail <= 0:
            continue
        success_rate = (succ / total) if total > 0 else 0.0
        if success_rate >= 0.67 and fail < 3:
            continue
        risk = 0.55 + min(0.35, fail * 0.05) + max(0.0, (0.5 - success_rate) * 0.4)
        entries.append(
            {
                "kind": "risky_playbook",
                "summary": f"Weak playbook: {str(row.get('action') or '').strip()}",
                "error": f"success_rate={success_rate:.2f}; fail_count={fail}",
                "task_type": _normalize_task(str(row.get("task_type") or "")),
                "created_at": str(row.get("updated_at") or ""),
                "risk_score": round(min(0.98, risk), 4),
                "avoid_action": str(row.get("action") or "").strip(),
                "source": "playbook_registry",
            }
        )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in entries:
        key = (
            str(item.get("kind") or ""),
            str(item.get("avoid_action") or ""),
            str(item.get("summary") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(
        key=lambda x: (
            float(x.get("risk_score") or 0.0),
            str(x.get("created_at") or ""),
        ),
        reverse=True,
    )
    deduped = deduped[:limit]

    avoid_actions = [str(x.get("avoid_action") or "").strip() for x in deduped if str(x.get("avoid_action") or "").strip()]
    avoid_actions = list(dict.fromkeys(avoid_actions))[:limit]
    blocked_patterns = [str(x.get("summary") or "").strip() for x in deduped if str(x.get("summary") or "").strip()]
    blocked_patterns = list(dict.fromkeys(blocked_patterns))[:limit]

    return {
        "agent": agent_low,
        "task_type": task_low,
        "entries": deduped,
        "avoid_actions": avoid_actions,
        "blocked_patterns": blocked_patterns,
        "signals": {
            "entry_count": len(deduped),
            "has_high_risk": any(float(x.get("risk_score") or 0.0) >= 0.8 for x in deduped),
        },
    }
