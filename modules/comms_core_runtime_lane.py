from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Статус"), KeyboardButton("Задачи")],
            [KeyboardButton("Создать"), KeyboardButton("Входы")],
            [KeyboardButton("Отчёт"), KeyboardButton("Еще")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


async def poll_owner_inbox(agent: Any) -> None:
    from modules.owner_inbox import mark_processed, read_pending_messages

    while True:
        try:
            for fp, text in read_pending_messages(limit=10):
                await agent._handle_owner_text(text, source="owner_inbox")
                mark_processed(fp)
        except Exception as e:
            agent._logger.warning(f"Owner inbox poll error: {e}", extra={"event": "owner_inbox_error"})
        await asyncio.sleep(5)


def is_owner(agent: Any, update: Update) -> bool:
    if not update.effective_chat:
        return False
    return update.effective_chat.id == agent._owner_id


def is_bot_sender(update: Update) -> bool:
    try:
        user = getattr(update, "effective_user", None)
        return bool(user and getattr(user, "is_bot", False))
    except Exception:
        return False


async def reject_stranger(agent: Any, update: Update) -> bool:
    if is_bot_sender(update):
        agent._logger.debug(
            "Игнорирую сообщение от bot-sender",
            extra={"event": "ignore_bot_sender"},
        )
        return True
    if is_owner(agent, update):
        return False
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    agent._logger.warning(
        f"Попытка доступа от чужого chat_id: {chat_id}",
        extra={"event": "unauthorized_access", "context": {"chat_id": chat_id}},
    )
    return True


def resolve_service_key(service_catalog: dict[str, dict[str, Any]], raw: str) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    if s in service_catalog:
        return s
    for service, meta in service_catalog.items():
        aliases = tuple(meta.get("aliases") or ())
        if s == service or s in aliases:
            return service
    return ""


async def cmd_kdp_login(agent: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return

    async def _reply(msg: str, markup=None) -> None:
        kwargs = {"reply_markup": markup} if markup is not None else {"reply_markup": agent._main_keyboard()}
        await update.message.reply_text(msg, **kwargs)

    otp = ""
    if context and getattr(context, "args", None):
        otp = agent._extract_otp_code(" ".join(context.args))
    if otp:
        agent._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat()}
        await agent._handle_kdp_login_flow(otp, _reply, with_button=True)
        return
    await agent._handle_kdp_login_flow("зайди на amazon kdp", _reply, with_button=True)


async def notify_error(agent: Any, module: str, error: str) -> bool:
    return await agent.send_message(
        f"Критическая ошибка в модуле {module}: {error}",
        level="error",
    )
