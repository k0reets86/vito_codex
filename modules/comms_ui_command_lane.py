from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from config.logger import get_logger

logger = get_logger(__name__)


async def cmd_status(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await update.message.reply_text(agent._render_unified_status(), reply_markup=agent._main_keyboard())
    logger.info("Команда /status выполнена", extra={"event": "cmd_status"})


async def cmd_prefs(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await agent._send_prefs(reply_to=update)


async def cmd_prefs_metrics(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await agent._send_prefs_metrics(reply_to=update)


async def cmd_packs(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    await agent._send_packs(reply_to=update)


async def cmd_llm_mode(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    args = list(getattr(context, "args", None) or [])
    mode = (args[0] if args else "status").strip().lower()
    ok, msg = agent._apply_llm_mode(mode)
    if not ok:
        await update.message.reply_text(msg, reply_markup=agent._main_keyboard())
        return
    await update.message.reply_text(msg, reply_markup=agent._main_keyboard())
    logger.info("LLM mode switched", extra={"event": "llm_mode_set", "context": {"mode": mode}})
