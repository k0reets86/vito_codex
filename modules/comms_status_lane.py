"""Reusable status/task command handlers for CommsAgent."""

from __future__ import annotations

from datetime import datetime, timezone

from config.settings import settings


async def cmd_report(agent, update) -> None:
    parts = ["VITO Report"]
    if agent._finance:
        parts.append(agent._finance.format_morning_finance())
    if agent._goal_engine:
        gs = agent._goal_engine.get_stats()
        parts.append(
            f"Цели: {gs['completed']} выполнено, {gs['executing']} в работе, "
            f"{gs['pending']} ожидают\nУспешность: {gs['success_rate']:.0%}"
        )
    if agent._owner_task_state:
        try:
            active = agent._owner_task_state.get_active()
            if active:
                parts.append(f"Текущая задача: {str(active.get('text', ''))[:200]}")
        except Exception:
            pass
    await agent._send_response(update, "\n\n".join(parts))


async def cmd_tasks(agent, update) -> None:
    if not agent._goal_engine:
        await update.message.reply_text("GoalEngine не подключён.", reply_markup=agent._main_keyboard())
        return
    from goal_engine import GoalStatus
    active_statuses = [GoalStatus.EXECUTING, GoalStatus.PENDING, GoalStatus.WAITING_APPROVAL, GoalStatus.PLANNING]
    active = []
    for status in active_statuses:
        active.extend(agent._goal_engine.get_all_goals(status=status))
    if not active:
        await update.message.reply_text("Нет активных задач.", reply_markup=agent._main_keyboard())
        return
    icon = {
        GoalStatus.EXECUTING: ">>",
        GoalStatus.PENDING: "..",
        GoalStatus.WAITING_APPROVAL: "??",
        GoalStatus.PLANNING: "~~",
    }
    lines = ["Активные задачи (все статусы):"]
    for g in active[:12]:
        lines.append(f"  [{icon.get(g.status, g.status.value)} {g.goal_id}] {g.title} (${g.estimated_cost_usd:.2f})")
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())


async def cmd_task_current(agent, update) -> None:
    if not agent._owner_task_state:
        await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=agent._main_keyboard())
        return
    active = agent._owner_task_state.get_active()
    if not active:
        await update.message.reply_text("Текущая задача не зафиксирована.", reply_markup=agent._main_keyboard())
        return
    msg = (
        "Текущая задача владельца:\n"
        f"- {str(active.get('text', ''))[:800]}\n"
        f"- intent: {active.get('intent', '')}\n"
        f"- status: {active.get('status', 'active')}\n"
        f"- service: {active.get('service_context', '') or 'n/a'}"
    )
    await update.message.reply_text(msg, reply_markup=agent._main_keyboard())


async def cmd_task_done(agent, update) -> None:
    if not agent._owner_task_state:
        await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=agent._main_keyboard())
        return
    agent._owner_task_state.complete(note="owner_marked_done")
    await update.message.reply_text("Текущая задача отмечена как выполненная.", reply_markup=agent._main_keyboard())


async def cmd_task_cancel(agent, update) -> None:
    if not agent._owner_task_state:
        await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=agent._main_keyboard())
        return
    agent._owner_task_state.cancel(note="owner_task_cancel")
    await update.message.reply_text("Текущая задача отменена.", reply_markup=agent._main_keyboard())


async def cmd_task_replace(agent, update) -> None:
    if not agent._owner_task_state:
        await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=agent._main_keyboard())
        return
    raw = (update.message.text or "").strip()
    new_task = raw.removeprefix("/task_replace").strip()
    if not new_task:
        await update.message.reply_text(
            "Использование: /task_replace <новая задача>",
            reply_markup=agent._main_keyboard(),
        )
        return
    metadata = {}
    if agent._has_fresh_service_context():
        metadata["service_context"] = agent._last_service_context
    agent._owner_task_state.set_active(new_task, source="telegram", intent="manual_replace", force=True, metadata=metadata)
    await update.message.reply_text("Текущая задача заменена.", reply_markup=agent._main_keyboard())


async def cmd_health(agent, update) -> None:
    parts = ["VITO Health Check"]
    if agent._decision_loop:
        st = agent._decision_loop.get_status()
        parts.append(f"Decision Loop: {'OK' if st['running'] else 'STOPPED'}")
    if agent._agent_registry:
        try:
            result = await agent._agent_registry.dispatch("health_check")
            parts.append(f"Health: {result.output if result and result.success else 'N/A'}")
        except Exception:
            parts.append("Health dispatch: N/A")
    if agent._llm_router:
        parts.append(f"LLM spend today: ${agent._llm_router.get_daily_spend():.2f}")
        parts.append(f"Daily limit OK: {agent._llm_router.check_daily_limit()}")
    agents_count = len(agent._agent_registry.get_all_statuses()) if agent._agent_registry else 0
    parts.append(f"Agents: {agents_count}")
    await update.message.reply_text("\n".join(parts), reply_markup=agent._main_keyboard())


async def cmd_errors(agent, update) -> None:
    if not agent._self_healer:
        await update.message.reply_text("SelfHealer не подключён.", reply_markup=agent._main_keyboard())
        return
    stats = agent._self_healer.get_error_stats()
    recent = stats.get("recent", [])
    unresolved = [e for e in recent if not e.get("resolved")][:10]
    if not unresolved:
        await update.message.reply_text("Нет нерешённых ошибок.", reply_markup=agent._main_keyboard())
        return
    lines = ["Нерешённые ошибки:"]
    for e in unresolved:
        lines.append(f"  [{e.get('module', '?')}] {e.get('error_type', '?')}: {e.get('message', '?')[:80]}")
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())


async def cmd_balances(agent, update) -> None:
    await update.message.reply_text("Проверяю балансы...", reply_markup=agent._main_keyboard())
    try:
        from modules.balance_checker import BalanceChecker
        text = (update.message.text or "").lower()
        show_env_keys = any(x in text for x in ("env", "keys", "raw"))
        checker = BalanceChecker()
        balances = await checker.check_all(include_env_keys=show_env_keys)
        internal = {}
        if agent._finance:
            internal["daily_spent"] = agent._finance.get_daily_spent()
            internal["daily_earned"] = agent._finance.get_daily_earned()
            internal["daily_limit"] = settings.DAILY_LIMIT_USD
        report = checker.format_report(balances, include_internal=internal, show_env_keys=show_env_keys)
        await update.message.reply_text(report, reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Ошибка проверки балансов: {e}", reply_markup=agent._main_keyboard())


def cancel_goal_queue(agent, reason: str = "owner_cancelled") -> int:
    if not agent._goal_engine:
        return 0
    try:
        from goal_engine import GoalStatus
        terminal = {GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED}
        cancelled = 0
        for goal in agent._goal_engine.get_all_goals():
            if goal.status in terminal:
                continue
            goal.status = GoalStatus.CANCELLED
            goal.completed_at = datetime.now(timezone.utc)
            goal.results = {"cancel_reason": reason}
            agent._goal_engine._persist_goal(goal)
            cancelled += 1
            try:
                if agent._decision_loop and getattr(agent._decision_loop, "orchestrator", None):
                    agent._decision_loop.orchestrator.cancel_session(goal.goal_id, reason=reason)
            except Exception:
                pass
            try:
                if agent._decision_loop and getattr(agent._decision_loop, "interrupts", None):
                    agent._decision_loop.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="cancelled")
            except Exception:
                pass
        return cancelled
    except Exception:
        return 0
