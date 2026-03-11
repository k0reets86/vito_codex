from __future__ import annotations

from datetime import datetime, timezone

from config.settings import settings
from llm_router import MODEL_REGISTRY
from modules.owner_preference_model import OwnerPreferenceModel


def build_operational_memory_context(engine, text: str, include_errors: bool = True) -> str:
    """Build short, actionable memory context that is actually used in prompts."""
    if not engine.memory:
        return ""
    blocks: list[str] = []
    try:
        similar = engine.memory.search_knowledge(text, n_results=3)
        if similar:
            blocks.append(
                "Из памяти VITO:\n"
                + "\n".join(
                    f"- {str(doc.get('text', ''))[:220]}" for doc in similar if isinstance(doc, dict)
                )
            )
    except Exception:
        pass
    try:
        skills = engine.memory.search_skills(text, limit=4)
        if skills:
            blocks.append(
                "Навыки VITO:\n"
                + "\n".join(
                    f"- {s.get('name')}: {str(s.get('description', ''))[:140]} "
                    f"(ok={int(s.get('success_count', 0) or 0)}, fail={int(s.get('fail_count', 0) or 0)})"
                    for s in skills
                    if isinstance(s, dict)
                )
            )
    except Exception:
        pass
    try:
        anti = engine.memory.get_patterns(category="anti_pattern", query=text, limit=3)
        if anti:
            blocks.append(
                "Антипаттерны (избегать):\n"
                + "\n".join(
                    f"- {p.get('pattern_key')}: {str(p.get('pattern_value', ''))[:170]}"
                    for p in anti
                    if isinstance(p, dict)
                )
            )
    except Exception:
        pass
    try:
        good = engine.memory.get_patterns(category="autonomy_success", query=text, limit=2)
        if good:
            blocks.append(
                "Успешные паттерны:\n"
                + "\n".join(
                    f"- {p.get('pattern_key')}: {str(p.get('pattern_value', ''))[:170]}"
                    for p in good
                    if isinstance(p, dict)
                )
            )
    except Exception:
        pass
    if include_errors:
        try:
            errs = engine.memory.get_recent_errors(limit=3, unresolved_only=True)
            if errs:
                blocks.append(
                    "Свежие нерешённые ошибки:\n"
                    + "\n".join(
                        f"- {e.get('module')}/{e.get('error_type')}: {str(e.get('message', ''))[:140]}"
                        for e in errs
                        if isinstance(e, dict)
                    )
                )
        except Exception:
            pass
    return ("\n\n".join(blocks)).strip()


def format_system_context(engine) -> str:
    parts = []

    now = datetime.now(timezone.utc)
    parts.append(
        f"Текущее время: {now.strftime('%Y-%m-%d %H:%M UTC')} "
        f"({now.strftime('%A')})"
    )

    try:
        daily_spend = engine.llm_router.get_daily_spend()
        breakdown = engine.llm_router.get_spend_breakdown(days=1)
        spend_lines = [
            f"LLM расходы сегодня: ${daily_spend:.4f} / ${settings.DAILY_LIMIT_USD:.2f} "
            f"(осталось: ${max(settings.DAILY_LIMIT_USD - daily_spend, 0):.4f})"
        ]
        if breakdown:
            for row in breakdown:
                spend_lines.append(
                    f"  {row['model']} [{row['task_type']}]: ${row['total_cost']:.4f} "
                    f"({row['calls']} вызовов, {row['total_input']}+{row['total_output']} токенов)"
                )
        else:
            spend_lines.append("  (нет вызовов сегодня)")
        parts.append("\n".join(spend_lines))
    except Exception:
        pass

    try:
        model_lines = ["Доступные модели:"]
        for _, m in MODEL_REGISTRY.items():
            model_lines.append(
                f"  {m.display_name} ({m.provider}): "
                f"${m.cost_per_1k_input:.4f}/1K in, ${m.cost_per_1k_output:.4f}/1K out"
            )
        parts.append("\n".join(model_lines))
    except Exception:
        pass

    if engine.finance:
        try:
            daily_spent = engine.finance.get_daily_spent()
            daily_earned = engine.finance.get_daily_earned()
            by_agent = engine.finance.get_spend_by_agent(days=1)
            by_cat = engine.finance.get_spend_by_category(days=1)
            pnl = engine.finance.get_pnl(days=7)
            products = engine.finance.get_product_roi()

            fin_lines = [f"Финансы: потрачено ${daily_spent:.4f}, заработано ${daily_earned:.2f}"]
            if by_agent:
                fin_lines.append("  По агентам:")
                for a in by_agent[:7]:
                    fin_lines.append(f"    {a['agent']}: ${a['total']:.4f} ({a['calls']} операций)")
            if by_cat:
                fin_lines.append("  По категориям:")
                for c in by_cat[:5]:
                    fin_lines.append(f"    {c['category']}: ${c['total']:.4f}")
            fin_lines.append(
                f"  P&L 7 дней: расход ${pnl['total_expenses']:.4f}, "
                f"доход ${pnl['total_income']:.2f}, "
                f"{'прибыль' if pnl['profitable'] else 'убыток'} ${abs(pnl['net_profit']):.4f}"
            )
            if products:
                fin_lines.append("  Продукты:")
                for p in products[:5]:
                    fin_lines.append(
                        f"    {p['name']} ({p['platform']}): "
                        f"доход ${p['revenue']:.2f}, ROI {p['roi_pct']:.0f}%"
                    )
            parts.append("\n".join(fin_lines))
        except Exception:
            pass

    if engine.goal_engine:
        try:
            stats = engine.goal_engine.get_stats()
            goals = engine.goal_engine.get_all_goals()
            goal_lines = [
                f"Цели: всего {stats['total']}, выполнено {stats['completed']}, "
                f"в работе {stats['executing']}, ожидают {stats['pending']}, "
                f"провалено {stats['failed']}, успешность {stats['success_rate']:.0%}"
            ]
            for g in goals[:12]:
                icon = {
                    "completed": "OK",
                    "failed": "XX",
                    "executing": ">>",
                    "pending": "..",
                    "waiting_approval": "??",
                    "planning": "~~",
                    "cancelled": "--",
                }.get(g.status.value, g.status.value)
                goal_lines.append(
                    f"  [{icon}] {g.goal_id[:8]} | {g.title} "
                    f"(приоритет: {g.priority.name}, ${g.estimated_cost_usd:.2f})"
                )
            parts.append("\n".join(goal_lines))
        except Exception:
            pass

    if engine.owner_task_state:
        try:
            active = engine.owner_task_state.get_active()
            if active:
                extra = ""
                if active.get("service_context"):
                    extra = f"\n  service_context: {str(active.get('service_context', ''))[:120]}"
                parts.append(
                    "Активная задача владельца:\n"
                    f"  text: {str(active.get('text', ''))[:300]}\n"
                    f"  intent: {str(active.get('intent', ''))}\n"
                    f"  status: {str(active.get('status', 'active'))}\n"
                    f"  updated_at: {str(active.get('updated_at', ''))}"
                    f"{extra}"
                )
        except Exception:
            pass

    if engine.agent_registry:
        try:
            statuses = engine.agent_registry.get_all_statuses()
            running = [s for s in statuses if s.get("status") == "running"]
            idle = [s for s in statuses if s.get("status") == "idle"]
            agent_lines = [f"Агенты: {len(statuses)} всего, {len(running)} работают, {len(idle)} ожидают"]
            for s in statuses:
                completed = s.get("tasks_completed", 0)
                cost = s.get("total_cost", 0)
                if completed > 0 or s.get("status") == "running":
                    agent_lines.append(
                        f"  {s['name']}: {s['status']} "
                        f"(задач: {completed}, ${cost:.4f})"
                    )
            parts.append("\n".join(agent_lines))
        except Exception:
            pass

    if engine.decision_loop:
        try:
            dl = engine.decision_loop.get_status()
            parts.append(
                f"Decision Loop: {'РАБОТАЕТ' if dl['running'] else 'ОСТАНОВЛЕН'}, "
                f"тиков: {dl['tick_count']}, потрачено: ${dl['daily_spend']:.4f}"
            )
        except Exception:
            pass

    if engine.self_healer:
        try:
            err = engine.self_healer.get_error_stats()
            err_lines = [
                f"Ошибки: {err['total']} всего, решено {err['resolved']}, "
                f"нерешено {err['unresolved']}, процент решения {err.get('resolution_rate', 0):.0%}"
            ]
            for e in err.get("recent", [])[:3]:
                if not e.get("resolved"):
                    err_lines.append(
                        f"  [{e.get('module', '?')}] {e.get('error_type', '?')}: "
                        f"{e.get('message', '?')[:80]}"
                    )
            parts.append("\n".join(err_lines))
        except Exception:
            pass

    if engine.memory:
        try:
            skills = engine.memory.get_top_skills(limit=5)
            if skills:
                skill_lines = ["Топ навыки:"]
                for s in skills:
                    skill_lines.append(
                        f"  {s['name']}: успех {s.get('success_count', 0)}, "
                        f"провал {s.get('fail_count', 0)}"
                    )
                parts.append("\n".join(skill_lines))
        except Exception:
            pass

    try:
        prefs = OwnerPreferenceModel().list_preferences(limit=5)
        if prefs:
            pref_line = "; ".join(f"{p.get('pref_key')}={p.get('value')}" for p in prefs)
            parts.append(f"Предпочтения владельца: {pref_line}")
    except Exception:
        pass

    if engine.self_updater:
        try:
            history = engine.self_updater.get_update_history(limit=3)
            if history:
                upd_lines = ["Последние обновления:"]
                for h in history:
                    upd_lines.append(
                        f"  {h.get('timestamp', '?')}: {h.get('description', '?')[:60]}"
                    )
                parts.append("\n".join(upd_lines))
        except Exception:
            pass

    return "\n\n".join(parts) if parts else "(система не инициализирована)"
