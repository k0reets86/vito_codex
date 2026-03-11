from __future__ import annotations

from datetime import datetime, timezone

from config.settings import settings
from modules.status_snapshot import build_status_snapshot, render_status_snapshot


def quick_answer(engine, text: str, lower: str) -> str:
    if any(w in lower for w in ("статус", "status", "health")):
        return quick_status(engine)
    if any(w in lower for w in ("расход", "spend", "budget", "лимит")):
        return quick_spend(engine)
    if any(w in lower for w in ("pnl", "прибыл", "доход", "revenue")):
        return quick_pnl(engine)
    if any(w in lower for w in ("balances", "баланс", "остатки", "счета")):
        return quick_balances(engine)
    if any(w in lower for w in ("цели", "goals", "задачи", "tasks")):
        return quick_goals(engine)
    if any(w in lower for w in ("агенты", "agents", "команда")):
        return quick_agents(engine)
    if any(w in lower for w in ("ошибк", "errors")):
        return quick_errors(engine)
    if any(w in lower for w in ("календар", "calendar", "сегодняшняя задача", "task today")):
        return quick_calendar(engine)

    if any(w in lower for w in ("праздник", "holiday", "календар")):
        try:
            from modules.calendar_knowledge import format_calendar_results, search_calendar

            results = search_calendar(text)
            return format_calendar_results(results)
        except Exception:
            pass
    else:
        try:
            from modules.calendar_knowledge import format_calendar_results, search_calendar

            results = search_calendar(text)
            if results:
                return format_calendar_results(results)
        except Exception:
            pass
    if any(w in lower for w in ("skills", "навык")):
        return quick_skills(engine)
    if any(w in lower for w in ("обновлен", "updates", "апдейт")):
        return quick_updates(engine)
    return ""


def quick_status(engine) -> str:
    pending = 0
    if engine.comms:
        pending = len(getattr(engine.comms, "_pending_approvals", {}) or {})
    snap = build_status_snapshot(
        decision_loop=engine.decision_loop,
        goal_engine=engine.goal_engine,
        llm_router=engine.llm_router,
        finance=engine.finance,
        owner_task_state=engine.owner_task_state,
        pending_approvals_count=pending,
    )
    return render_status_snapshot(snap, title="VITO Status (fast)")


def quick_spend(engine) -> str:
    spend = engine.llm_router.get_daily_spend() if engine.llm_router else 0.0
    limit = settings.DAILY_LIMIT_USD
    return f"Расходы сегодня: ${spend:.2f} / ${limit:.2f} (осталось ${max(limit - spend, 0):.2f})"


def quick_pnl(engine) -> str:
    if not engine.finance:
        return "FinancialController не подключён."
    pnl = engine.finance.get_pnl(days=30)
    return (
        f"P&L за 30 дней: расход ${pnl['total_expenses']:.2f}, "
        f"доход ${pnl['total_income']:.2f}, "
        f"{'прибыль' if pnl['profitable'] else 'убыток'} ${abs(pnl['net_profit']):.2f}"
    )


def quick_balances(engine) -> str:
    if not engine.finance:
        return "FinancialController не подключён."
    daily_spent = engine.finance.get_daily_spent()
    daily_earned = engine.finance.get_daily_earned()
    limit = settings.DAILY_LIMIT_USD
    return (
        f"Внутренние балансы (без внешних API):\n"
        f"- Потрачено сегодня: ${daily_spent:.2f}\n"
        f"- Доход сегодня: ${daily_earned:.2f}\n"
        f"- Лимит: ${limit:.2f} (осталось ${max(limit - daily_spent, 0):.2f})"
    )


def quick_goals(engine) -> str:
    if not engine.goal_engine:
        return "GoalEngine не подключён."
    goals = engine.goal_engine.get_all_goals()[:10]
    if not goals:
        return "Нет целей."
    lines = []
    for g in goals:
        icon = {
            "completed": "done",
            "failed": "fail",
            "executing": ">>",
            "pending": "..",
            "waiting_approval": "??",
            "planning": "~~",
        }.get(g.status.value, g.status.value)
        lines.append(f"[{icon}] {g.title} (${g.estimated_cost_usd:.2f})")
    return "Цели:\n" + "\n".join(lines)


def quick_agents(engine) -> str:
    if not engine.agent_registry:
        return "AgentRegistry не подключён."
    statuses = engine.agent_registry.get_all_statuses()
    if not statuses:
        return "Нет зарегистрированных агентов."
    lines = [f"Агенты ({len(statuses)}):"]
    for s in statuses:
        icon = {"idle": "o", "running": ">>", "stopped": "x", "error": "!"}.get(s["status"], "?")
        lines.append(f"[{icon}] {s['name']} — {s['status']}")
    return "\n".join(lines)


def quick_errors(engine) -> str:
    if not engine.self_healer:
        return "SelfHealer не подключён."
    stats = engine.self_healer.get_error_stats()
    unresolved = stats.get("unresolved", 0)
    return (
        f"Ошибки: всего {stats.get('total', 0)}, "
        f"нерешено {unresolved}, решено {stats.get('resolved', 0)}"
    )


def quick_calendar(engine) -> str:
    try:
        import sqlite3

        conn = sqlite3.connect(settings.SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT * FROM weekly_calendar WHERE date = ? LIMIT 1",
            (today,),
        ).fetchone()
        conn.close()
        if row:
            return f"Сегодня: {row['title']} — {row['description'][:200]}"
        return "Сегодня в календаре задач нет."
    except Exception:
        return "Календарь недоступен."


def quick_skills(engine) -> str:
    if not engine.memory:
        return "Memory не подключена."
    skills = engine.memory.get_top_skills(limit=5)
    if not skills:
        return "Навыки пока не накоплены."
    lines = [f"{s['name']}: успех {s.get('success_count', 0)}, провал {s.get('fail_count', 0)}" for s in skills]
    return "Топ навыки:\n" + "\n".join(lines)


def quick_updates(engine) -> str:
    if not engine.self_updater:
        return "SelfUpdater не подключён."
    history = engine.self_updater.get_update_history(limit=3)
    if not history:
        return "История обновлений пуста."
    lines = [f"{h.get('timestamp', '?')}: {h.get('description', '')[:80]}" for h in history]
    return "Последние обновления:\n" + "\n".join(lines)
