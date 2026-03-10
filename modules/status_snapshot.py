"""Shared status snapshot/renderer for ConversationEngine and CommsAgent."""

from __future__ import annotations

from typing import Any


def build_status_snapshot(
    *,
    decision_loop=None,
    goal_engine=None,
    llm_router=None,
    finance=None,
    owner_task_state=None,
    pending_approvals_count: int = 0,
) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "running": False,
        "tick_count": 0,
        "daily_spend": 0.0,
        "goals_total": 0,
        "goals_completed": 0,
        "goals_executing": 0,
        "goals_pending": 0,
        "goals_waiting_approval": 0,
        "llm_spend": 0.0,
        "finance_spend": 0.0,
        "pending_approvals": int(pending_approvals_count or 0),
        "owner_task_text": "",
        "platform_readiness": {
            "total": 0,
            "owner_grade": 0,
            "can_validate_now": 0,
            "blocked": 0,
            "next_steps": [],
        },
    }

    if decision_loop:
        try:
            st = decision_loop.get_status() or {}
            snap["running"] = bool(st.get("running", False))
            snap["tick_count"] = int(st.get("tick_count", 0) or 0)
            snap["daily_spend"] = float(st.get("daily_spend", 0.0) or 0.0)
            pr = dict(st.get("platform_readiness") or {})
            if pr:
                snap["platform_readiness"] = {
                    "total": int(pr.get("total", 0) or 0),
                    "owner_grade": int(pr.get("owner_grade", 0) or 0),
                    "can_validate_now": int(pr.get("can_validate_now", 0) or 0),
                    "blocked": int(pr.get("blocked", 0) or 0),
                    "next_steps": list(pr.get("next_steps") or [])[:5],
                }
        except Exception:
            pass

    if goal_engine:
        try:
            if hasattr(goal_engine, "reload_goals"):
                goal_engine.reload_goals()
        except Exception:
            pass
        try:
            goals = goal_engine.get_all_goals() or []
            counts: dict[str, int] = {}
            for g in goals:
                key = str(getattr(getattr(g, "status", None), "value", "") or "")
                if key:
                    counts[key] = counts.get(key, 0) + 1
            snap["goals_total"] = len(goals)
            snap["goals_completed"] = int(counts.get("completed", 0))
            snap["goals_executing"] = int(counts.get("executing", 0))
            snap["goals_pending"] = int(counts.get("pending", 0))
            snap["goals_waiting_approval"] = int(counts.get("waiting_approval", 0))
        except Exception:
            pass

    if llm_router:
        try:
            snap["llm_spend"] = float(llm_router.get_daily_spend() or 0.0)
        except Exception:
            pass

    if finance:
        try:
            snap["finance_spend"] = float(finance.get_daily_spent() or 0.0)
        except Exception:
            pass

    if owner_task_state:
        try:
            active = owner_task_state.get_active()
            if active:
                snap["owner_task_text"] = str(active.get("text", "") or "")[:120]
        except Exception:
            pass

    return snap


def render_status_snapshot(snapshot: dict[str, Any], *, title: str = "VITO Status") -> str:
    snap = dict(snapshot or {})
    running = bool(snap.get("running", False))
    tick_count = int(snap.get("tick_count", 0) or 0)
    daily_spend = float(snap.get("daily_spend", 0.0) or 0.0)
    goals_total = int(snap.get("goals_total", 0) or 0)
    goals_completed = int(snap.get("goals_completed", 0) or 0)
    goals_executing = int(snap.get("goals_executing", 0) or 0)
    goals_pending = int(snap.get("goals_pending", 0) or 0)
    goals_waiting_approval = int(snap.get("goals_waiting_approval", 0) or 0)
    llm_spend = float(snap.get("llm_spend", 0.0) or 0.0)
    finance_spend = float(snap.get("finance_spend", 0.0) or 0.0)
    pending_approvals = int(snap.get("pending_approvals", 0) or 0)
    owner_task_text = str(snap.get("owner_task_text", "") or "").strip()
    platform_readiness = dict(snap.get("platform_readiness") or {})

    parts = [
        title,
        (
            f"Decision Loop: {'работает' if running else 'остановлен'}\n"
            f"Тиков: {tick_count}\n"
            f"Потрачено сегодня: ${daily_spend:.2f}"
        ),
        (
            f"Цели: {goals_total} всего, {goals_completed} выполнено, "
            f"{goals_executing} в работе, {goals_pending} ожидают, "
            f"{goals_waiting_approval} ждут одобрения"
        ),
    ]

    if llm_spend > 0 or finance_spend > 0:
        parts.append(f"Траты сегодня: LLM ${llm_spend:.2f}; Финконтроль ${finance_spend:.2f}")
    if pending_approvals > 0:
        parts.append(f"Ожидают одобрения: {pending_approvals}")
    if owner_task_text:
        parts.append(f"Текущая задача: {owner_task_text}")
    if any(platform_readiness.values()):
        total = int(platform_readiness.get("total", 0) or 0)
        owner_grade = int(platform_readiness.get("owner_grade", 0) or 0)
        ready_now = int(platform_readiness.get("can_validate_now", 0) or 0)
        blocked = int(platform_readiness.get("blocked", 0) or 0)
        next_steps = list(platform_readiness.get("next_steps") or [])[:3]
        line = (
            f"Платформы: {total} всего; owner-grade {owner_grade}; "
            f"готовы к валидации {ready_now}; блокеры {blocked}"
        )
        if next_steps:
            line += f"\nСледующее: {', '.join(next_steps)}"
        parts.append(line)

    return "\n\n".join(parts)
