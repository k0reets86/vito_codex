from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def handle_deterministic_message_routes(agent, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, *, strict_cmds: bool) -> bool:
    lower = text.strip().lower()

    if (not strict_cmds) and any(x in lower for x in ("llm_mode ", "режим llm", "режим lmm", "llm режим")):
        mode = "status"
        if any(x in lower for x in (" free", " тест", " gemini", " flash")):
            mode = "free"
        elif any(x in lower for x in (" prod", " боев", " production")):
            mode = "prod"
        ok, msg = agent._apply_llm_mode(mode)
        await update.message.reply_text(
            msg if ok else "Используй: /llm_mode free|prod|status",
            reply_markup=agent._main_keyboard(),
        )
        return True

    if (not strict_cmds) and any(kw in lower for kw in ["баланс", "balance", "balances", "остатки", "сколько на счетах", "сколько осталось"]):
        await agent._cmd_balances(update, context)
        return True

    for candidate in (
        agent._maybe_handle_owner_shortcuts,
        agent._maybe_handle_owner_service_commands,
        agent._maybe_handle_owner_menu_commands,
        agent._maybe_handle_owner_task_commands,
        agent._maybe_handle_owner_publish_commands,
        agent._maybe_handle_owner_webop_commands,
    ):
        handled = await candidate(text)
        if handled:
            return True

    if agent._pending_approvals:
        if agent._is_yes_token(lower):
            await agent._cmd_approve(update, context)
            return True
        if agent._is_no_token(lower):
            await agent._cmd_reject(update, context)
            return True

    if agent._goal_engine:
        from goal_engine import GoalStatus
        waiting = [g for g in agent._goal_engine.get_all_goals() if g.status == GoalStatus.WAITING_APPROVAL]
        if waiting and agent._is_yes_token(lower):
            goal = waiting[0]
            goal.status = GoalStatus.PENDING
            agent._goal_engine._persist_goal(goal)
            await update.message.reply_text(
                f"✅ Одобрено: {goal.title}\nПриступаю к выполнению.",
                reply_markup=agent._main_keyboard(),
            )
            return True
        if waiting and agent._is_no_token(lower):
            goal = waiting[0]
            agent._goal_engine.fail_goal(goal.goal_id, "Отклонено владельцем")
            await update.message.reply_text(
                f"❌ Отклонено: {goal.title}",
                reply_markup=agent._main_keyboard(),
            )
            return True

    cmd = agent._resolve_button_command(text)
    if cmd:
        if cmd == "help":
            await update.message.reply_text(agent._render_help(), reply_markup=agent._main_keyboard())
            return True
        if cmd == "help_daily":
            await update.message.reply_text(agent._render_help("daily"), reply_markup=agent._main_keyboard())
            return True
        if cmd == "help_rare":
            await update.message.reply_text(agent._render_help("rare"), reply_markup=agent._main_keyboard())
            return True
        if cmd == "help_system":
            await update.message.reply_text(agent._render_help("system"), reply_markup=agent._main_keyboard())
            return True
        if cmd == "auth_hub":
            await update.message.reply_text(agent._render_auth_hub(), reply_markup=agent._main_keyboard())
            return True
        if cmd == "research_hub":
            await update.message.reply_text(agent._render_research_hub(), reply_markup=agent._main_keyboard())
            return True
        if cmd == "create_hub":
            await update.message.reply_text(agent._render_create_hub(), reply_markup=agent._main_keyboard())
            return True
        if cmd == "platforms_hub":
            await update.message.reply_text(agent._render_platforms_hub(), reply_markup=agent._main_keyboard())
            return True
        if cmd == "more":
            await update.message.reply_text(agent._render_more_menu(), reply_markup=agent._main_keyboard())
            return True
        handler = {
            "start": agent._cmd_start,
            "status": agent._cmd_status,
            "goals": agent._cmd_goals,
            "tasks": agent._cmd_tasks,
            "report": agent._cmd_report,
            "spend": agent._cmd_spend,
            "approve": agent._cmd_approve,
            "reject": agent._cmd_reject,
        }.get(cmd)
        if handler:
            await handler(update, context)
            return True
        await update.message.reply_text(
            "Отправь текст цели, и я создам её.",
            reply_markup=agent._main_keyboard(),
        )
        return True

    return False
