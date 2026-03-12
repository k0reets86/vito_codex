from __future__ import annotations

from typing import Any

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeDefault
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config.settings import settings


async def start(agent: Any) -> None:
    """Запускает Telegram polling."""
    if not settings.TELEGRAM_BOT_TOKEN:
        agent._logger.warning(
            "TELEGRAM_BOT_TOKEN не задан — бот не запущен",
            extra={"event": "no_token"},
        )
        return

    agent._app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    agent._bot = agent._app.bot

    agent._app.add_handler(CommandHandler("start", agent._cmd_start))
    agent._app.add_handler(CommandHandler("help", agent._cmd_help))
    agent._app.add_handler(CommandHandler("help_daily", agent._cmd_help_daily))
    agent._app.add_handler(CommandHandler("help_rare", agent._cmd_help_rare))
    agent._app.add_handler(CommandHandler("help_system", agent._cmd_help_system))
    agent._app.add_handler(CommandHandler("main", agent._cmd_start))
    agent._app.add_handler(CommandHandler("status", agent._cmd_status))
    agent._app.add_handler(CommandHandler("goals", agent._cmd_goals))
    agent._app.add_handler(CommandHandler("spend", agent._cmd_spend))
    agent._app.add_handler(CommandHandler("approve", agent._cmd_approve))
    agent._app.add_handler(CommandHandler("reject", agent._cmd_reject))
    agent._app.add_handler(CommandHandler("goal", agent._cmd_goal))
    agent._app.add_handler(CommandHandler("agents", agent._cmd_agents))
    agent._app.add_handler(CommandHandler("skill_matrix_v2", agent._cmd_skill_matrix_v2))
    agent._app.add_handler(CommandHandler("skill_eval", agent._cmd_skill_eval))
    agent._app.add_handler(CommandHandler("report", agent._cmd_report))
    agent._app.add_handler(CommandHandler("stop", agent._cmd_stop))
    agent._app.add_handler(CommandHandler("cancel", agent._cmd_cancel))
    agent._app.add_handler(CommandHandler("resume", agent._cmd_resume))
    agent._app.add_handler(CommandHandler("budget", agent._cmd_budget))
    agent._app.add_handler(CommandHandler("tasks", agent._cmd_tasks))
    agent._app.add_handler(CommandHandler("trends", agent._cmd_trends))
    agent._app.add_handler(CommandHandler("earnings", agent._cmd_earnings))
    agent._app.add_handler(CommandHandler("deep", agent._cmd_deep))
    agent._app.add_handler(CommandHandler("brainstorm", agent._cmd_brainstorm))
    agent._app.add_handler(CommandHandler("healer", agent._cmd_healer))
    agent._app.add_handler(CommandHandler("logs", agent._cmd_logs))
    agent._app.add_handler(CommandHandler("backup", agent._cmd_backup))
    agent._app.add_handler(CommandHandler("rollback", agent._cmd_rollback))
    agent._app.add_handler(CommandHandler("health", agent._cmd_health))
    agent._app.add_handler(CommandHandler("errors", agent._cmd_errors))
    agent._app.add_handler(CommandHandler("balances", agent._cmd_balances))
    agent._app.add_handler(CommandHandler("goals_all", agent._cmd_goals_all))
    agent._app.add_handler(CommandHandler("fix", agent._cmd_fix))
    agent._app.add_handler(CommandHandler("skills", agent._cmd_skills))
    agent._app.add_handler(CommandHandler("skills_pending", agent._cmd_skills_pending))
    agent._app.add_handler(CommandHandler("skills_audit", agent._cmd_skills_audit))
    agent._app.add_handler(CommandHandler("skills_fix", agent._cmd_skills_fix))
    agent._app.add_handler(CommandHandler("playbooks", agent._cmd_playbooks))
    agent._app.add_handler(CommandHandler("recipes", agent._cmd_recipes))
    agent._app.add_handler(CommandHandler("recipe_run", agent._cmd_recipe_run))
    agent._app.add_handler(CommandHandler("workflow", agent._cmd_workflow))
    agent._app.add_handler(CommandHandler("handoffs", agent._cmd_handoffs))
    agent._app.add_handler(CommandHandler("prefs", agent._cmd_prefs))
    agent._app.add_handler(CommandHandler("prefs_metrics", agent._cmd_prefs_metrics))
    agent._app.add_handler(CommandHandler("packs", agent._cmd_packs))
    agent._app.add_handler(CommandHandler("pubq", agent._cmd_pubq))
    agent._app.add_handler(CommandHandler("pubrun", agent._cmd_pubrun))
    agent._app.add_handler(CommandHandler("webop", agent._cmd_webop))
    agent._app.add_handler(CommandHandler("task_current", agent._cmd_task_current))
    agent._app.add_handler(CommandHandler("task_done", agent._cmd_task_done))
    agent._app.add_handler(CommandHandler("task_cancel", agent._cmd_task_cancel))
    agent._app.add_handler(CommandHandler("task_replace", agent._cmd_task_replace))
    agent._app.add_handler(CommandHandler("clear_goals", agent._cmd_clear_goals))
    agent._app.add_handler(CommandHandler("nettest", agent._cmd_nettest))
    agent._app.add_handler(CommandHandler("smoke", agent._cmd_smoke))
    agent._app.add_handler(CommandHandler("llm_mode", agent._cmd_llm_mode))
    agent._app.add_handler(CommandHandler("kdp_login", agent._cmd_kdp_login))
    agent._app.add_handler(CommandHandler("auth", agent._cmd_auth))
    agent._app.add_handler(CommandHandler("auth_status", agent._cmd_auth_status))
    agent._app.add_handler(CommandHandler("auth_cookie", agent._cmd_auth_cookie))
    agent._app.add_handler(
        MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, agent._on_attachment)
    )
    agent._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, agent._on_message))
    agent._app.add_handler(CallbackQueryHandler(agent._handle_callback))
    agent._app.add_error_handler(agent._on_app_error)

    await agent._app.initialize()
    try:
        await agent._bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    command_catalog = [
        BotCommand("help", "Справка по командам и сценариям"),
        BotCommand("help_daily", "Ежедневные команды"),
        BotCommand("help_rare", "Редкие команды"),
        BotCommand("help_system", "Системные команды"),
        BotCommand("status", "Статус системы"),
        BotCommand("goals", "Активные цели"),
        BotCommand("goal", "Создать цель"),
        BotCommand("spend", "Расходы за сегодня"),
        BotCommand("report", "Сводный отчёт"),
        BotCommand("approve", "Одобрить ожидающий запрос"),
        BotCommand("reject", "Отклонить ожидающий запрос"),
        BotCommand("cancel", "Пауза текущих задач"),
        BotCommand("resume", "Возобновить работу"),
        BotCommand("task_current", "Текущая задача владельца"),
        BotCommand("task_done", "Закрыть текущую задачу"),
        BotCommand("balances", "Балансы сервисов"),
        BotCommand("llm_mode", "Режим LLM: free/prod"),
        BotCommand("kdp_login", "Вход в Amazon KDP"),
        BotCommand("auth", "Вход: status/refresh/verify"),
        BotCommand("health", "Проверка здоровья системы"),
        BotCommand("logs", "Последние логи"),
    ]
    await agent._bot.set_my_commands(command_catalog, scope=BotCommandScopeDefault())
    await agent._bot.set_my_commands(command_catalog, scope=BotCommandScopeAllPrivateChats())

    await agent._app.start()
    if agent._app.updater:
        await agent._app.updater.start_polling(drop_pending_updates=True)
    agent._logger.info(
        "Telegram polling запущен",
        extra={"event": "telegram_started", "context": {"owner_id": int(agent._owner_id)}},
    )
