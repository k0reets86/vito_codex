from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import ContextTypes


async def cmd_start(agent: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await update.message.reply_text(
        "VITO на связи.\n\n"
        "Главные сценарии теперь вынесены в меню:\n"
        "- Исследовать\n"
        "- Создать\n"
        "- Платформы\n"
        "- Входы\n\n"
        "Быстрый старт:\n"
        "/status\n"
        "/goals\n"
        "/goal <текст>\n"
        "/tasks\n"
        "/report\n\n"
        "Если нужен каталог команд:\n"
        "/help — обзор\n"
        "/help_daily — ежедневные\n"
        "/help_rare — редкие\n"
        "/help_system — системные",
        reply_markup=agent._main_keyboard(),
    )


async def cmd_help(agent: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    args = getattr(context, "args", None) or []
    topic = args[0] if args else None
    text = agent._render_help(topic=topic)
    if topic:
        await update.message.reply_text(text, reply_markup=agent._main_keyboard())
        return
    await update.message.reply_text(text, reply_markup=agent._help_inline_keyboard())


async def cmd_help_daily(agent: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await update.message.reply_text(agent._render_help("daily"), reply_markup=agent._main_keyboard())


async def cmd_help_rare(agent: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await update.message.reply_text(agent._render_help("rare"), reply_markup=agent._main_keyboard())


async def cmd_help_system(agent: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await update.message.reply_text(agent._render_help("system"), reply_markup=agent._main_keyboard())
