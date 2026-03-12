from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from config.settings import settings
from telegram import Update
from telegram.ext import ContextTypes


async def cmd_budget(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._finance:
        await update.message.reply_text("FinancialController не подключён.", reply_markup=agent._main_keyboard())
        return
    check = agent._finance.check_expense(0)
    pnl = agent._finance.get_pnl(days=30)
    text = (
        f"Бюджет\n"
        f"Сегодня: ${check.get('daily_spent', 0):.2f} / ${settings.DAILY_LIMIT_USD:.2f}\n"
        f"Осталось: ${check.get('remaining', 0):.2f}\n\n"
        f"P&L за 30 дней:\n"
        f"Расходы: ${pnl['total_expenses']:.2f}\n"
        f"Доходы: ${pnl['total_income']:.2f}\n"
        f"{'Прибыль' if pnl['profitable'] else 'Убыток'}: ${abs(pnl['net_profit']):.2f}"
    )
    await update.message.reply_text(text, reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /budget выполнена", extra={"event": "cmd_budget"})


async def cmd_trends(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._agent_registry:
        await update.message.reply_text("AgentRegistry не подключён.", reply_markup=agent._main_keyboard())
        return
    await update.message.reply_text("Сканирую тренды...", reply_markup=agent._main_keyboard())
    try:
        result = await agent._agent_registry.dispatch("trend_scan")
        if result and result.success:
            output = str(result.output)[:3000]
            await update.message.reply_text(f"Тренды:\n{output}", reply_markup=agent._main_keyboard())
        else:
            await update.message.reply_text("Не удалось просканировать тренды.", reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}", reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /trends выполнена", extra={"event": "cmd_trends"})


async def cmd_healer(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._self_healer:
        await update.message.reply_text("SelfHealer не подключён.", reply_markup=agent._main_keyboard())
        return
    stats = agent._self_healer.get_error_stats()
    text = (
        f"SelfHealer Stats\n"
        f"Всего ошибок: {stats['total']}\n"
        f"Решено: {stats['resolved']}\n"
        f"Не решено: {stats['unresolved']}\n"
        f"Процент решения: {stats.get('resolution_rate', 0):.0%}\n"
        f"В очереди: {stats.get('pending_retries', 0)}"
    )
    await update.message.reply_text(text, reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /healer выполнена", extra={"event": "cmd_healer"})


async def cmd_logs(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    log_path = Path("logs/vito.log")
    if not log_path.exists():
        await update.message.reply_text("Лог-файл не найден.", reply_markup=agent._main_keyboard())
        return
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        last_lines = lines[-20:]
        text = "".join(last_lines)[-3000:]
        await update.message.reply_text(f"Последние логи:\n{text}", reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Ошибка чтения логов: {e}", reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /logs выполнена", extra={"event": "cmd_logs"})


async def cmd_backup(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if agent._agent_registry:
        try:
            result = await agent._agent_registry.dispatch("backup")
            if result and result.success:
                await update.message.reply_text(f"Бэкап создан: {result.output}", reply_markup=agent._main_keyboard())
                return
        except Exception:
            pass
    if agent._self_updater:
        backup_path = agent._self_updater.backup_current_code()
        if backup_path:
            await update.message.reply_text(f"Бэкап создан: {backup_path}", reply_markup=agent._main_keyboard())
        else:
            await update.message.reply_text("Не удалось создать бэкап.", reply_markup=agent._main_keyboard())
    else:
        await update.message.reply_text("SelfUpdater не подключён.", reply_markup=agent._main_keyboard())
    agent._logger.info("Команда /backup выполнена", extra={"event": "cmd_backup"})


async def cmd_rollback(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._self_updater:
        await update.message.reply_text("SelfUpdater не подключён.", reply_markup=agent._main_keyboard())
        return
    history = agent._self_updater.get_update_history(limit=1)
    if not history:
        await update.message.reply_text("Нет истории обновлений для отката.", reply_markup=agent._main_keyboard())
        return
    last = history[0]
    backup_path = last.get("backup_path", "")
    if not backup_path:
        await update.message.reply_text("Нет бэкапа для отката.", reply_markup=agent._main_keyboard())
        return
    if not agent._is_confirmed(getattr(context, "args", None)):
        agent._pending_owner_confirmation = {
            "kind": "rollback",
            "backup_path": backup_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await update.message.reply_text(
            "Откат меняет код и может удалить последние доработки.\n"
            "Подтверди: `/rollback yes` или ответь `да` на это сообщение.",
            reply_markup=agent._main_keyboard(),
        )
        return
    success = agent._self_updater.rollback(backup_path)
    status = "Откат выполнен" if success else "Ошибка отката"
    await update.message.reply_text(f"{status}: {backup_path}", reply_markup=agent._main_keyboard())
    agent._logger.info(f"Команда /rollback: {status}", extra={"event": "cmd_rollback"})
