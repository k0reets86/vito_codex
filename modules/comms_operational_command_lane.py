from __future__ import annotations

import asyncio

from modules.comms_status_lane import (
    cancel_goal_queue as _cancel_goal_queue_impl,
    cmd_balances as _cmd_balances_impl,
    cmd_errors as _cmd_errors_impl,
    cmd_health as _cmd_health_impl,
    cmd_task_cancel as _cmd_task_cancel_impl,
    cmd_task_current as _cmd_task_current_impl,
    cmd_task_done as _cmd_task_done_impl,
    cmd_task_replace as _cmd_task_replace_impl,
    cmd_tasks as _cmd_tasks_impl,
)


async def cmd_stop(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._is_confirmed(getattr(context, "args", None)):
        await update.message.reply_text(
            "Подтверди остановку цикла: `/stop yes`",
            reply_markup=agent._main_keyboard(),
        )
        return
    if agent._decision_loop:
        agent._decision_loop.stop()
        await update.message.reply_text("Decision Loop остановлен.", reply_markup=agent._main_keyboard())
    else:
        await update.message.reply_text("Decision Loop не подключён.", reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /stop выполнена", extra={"event": "cmd_stop"})


async def cmd_cancel(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    cancelled_goals = agent._cancel_all_owner_work(reason="owner_cancelled")
    await update.message.reply_text(
        f"Всё приостановлено. Отправь /resume, когда будешь готов продолжить.\n"
        f"Отменено задач из очереди: {cancelled_goals}.",
        reply_markup=agent._main_keyboard(),
    )
    agent._logger.info("Команда /cancel выполнена", extra={"event": "cmd_cancel"})


def cancel_goal_queue(agent, reason: str = "owner_cancelled") -> int:
    return _cancel_goal_queue_impl(agent, reason=reason)


async def cmd_resume(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    if agent._cancel_state:
        agent._cancel_state.clear()
    if agent._decision_loop and not agent._decision_loop.running:
        asyncio.create_task(agent._decision_loop.run())
        await update.message.reply_text("Decision Loop возобновлён.", reply_markup=agent._main_keyboard())
    elif agent._decision_loop and agent._decision_loop.running:
        await update.message.reply_text("Decision Loop уже работает.", reply_markup=agent._main_keyboard())
    else:
        await update.message.reply_text("Decision Loop не подключён.", reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /resume выполнена", extra={"event": "cmd_resume"})


async def cmd_tasks(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_tasks_impl(agent, update)
    agent._logger.info("Команда /tasks выполнена", extra={"event": "cmd_tasks"})


async def cmd_task_current(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_task_current_impl(agent, update)


async def cmd_task_done(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_task_done_impl(agent, update)


async def cmd_task_cancel(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_task_cancel_impl(agent, update)


async def cmd_task_replace(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_task_replace_impl(agent, update)


async def cmd_earnings(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._finance:
        await update.message.reply_text("FinancialController не подключён.", reply_markup=agent._main_keyboard())
        return
    trend = agent._finance.get_revenue_trend(7)
    if not trend:
        await update.message.reply_text("Нет данных о доходах за 7 дней.", reply_markup=agent._main_keyboard())
        return
    lines = ["Доходы за 7 дней:"]
    for day in trend:
        lines.append(f"  {day['date']}: ${day.get('earned_usd', 0):.2f} (расход: ${day.get('spent_usd', 0):.2f})")
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /earnings выполнена", extra={"event": "cmd_earnings"})


async def cmd_health(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_health_impl(agent, update)
    agent._logger.info("Команда /health выполнена", extra={"event": "cmd_health"})


async def cmd_errors(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_errors_impl(agent, update)
    agent._logger.info("Команда /errors выполнена", extra={"event": "cmd_errors"})


async def cmd_balances(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    await _cmd_balances_impl(agent, update)
    agent._logger.info("Команда /balances выполнена", extra={"event": "cmd_balances"})
