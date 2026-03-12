from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import settings


async def request_approval(agent, request_id: str, message: str, timeout_seconds: int = 3600) -> Optional[bool]:
    """Запрашивает одобрение у владельца. Возвращает True/False/None (timeout)."""
    import os

    if os.getenv("AUTO_APPROVE_TESTS") == "1":
        agent._logger.info(
            "Auto-approve enabled for tests",
            extra={"event": "approval_auto", "context": {"request_id": request_id}},
        )
        if timeout_seconds <= 0:
            return None
        return True

    channel = agent._approval_channel(request_id)
    if channel:
        cooldown_sec = int(getattr(settings, "APPROVAL_REPEAT_COOLDOWN_SEC", 1800) or 1800)
        if any(str(k).lower().startswith(f"{channel}_") for k in (agent._pending_approvals or {}).keys()):
            agent._logger.info(
                "Approval suppressed: channel already pending",
                extra={"event": "approval_suppressed_pending", "context": {"request_id": request_id, "channel": channel}},
            )
            return None
        last_iso = str(agent._approval_last_sent_at.get(channel, "") or "").strip()
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if age < max(60, cooldown_sec):
                    agent._logger.info(
                        "Approval suppressed by cooldown",
                        extra={
                            "event": "approval_suppressed_cooldown",
                            "context": {"request_id": request_id, "channel": channel, "age_sec": int(age)},
                        },
                    )
                    return None
            except Exception:
                pass

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    agent._pending_approvals[request_id] = future
    if channel:
        agent._approval_last_sent_at[channel] = datetime.now(timezone.utc).isoformat()

    inline_kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Одобрить", callback_data=f"approve:{request_id}"),
            InlineKeyboardButton("Отклонить", callback_data=f"reject:{request_id}"),
        ]]
    )
    if agent._bot:
        try:
            await agent._bot.send_message(
                chat_id=agent._owner_id,
                text=message,
                reply_markup=inline_kb,
            )
        except Exception:
            await agent.send_message(message, level="approval")
    else:
        await agent.send_message(message, level="approval")

    agent._logger.info(
        f"Запрос одобрения: {request_id}",
        extra={"event": "approval_requested", "context": {"request_id": request_id}},
    )

    if timeout_seconds <= 0:
        agent._pending_approvals.pop(request_id, None)
        agent._logger.warning(
            f"Таймаут одобрения: {request_id}",
            extra={"event": "approval_timeout", "context": {"request_id": request_id}},
        )
        return None

    try:
        result = await asyncio.wait_for(future, timeout=timeout_seconds)
        return result
    except asyncio.TimeoutError:
        agent._pending_approvals.pop(request_id, None)
        agent._logger.warning(
            f"Таймаут одобрения: {request_id}",
            extra={"event": "approval_timeout", "context": {"request_id": request_id}},
        )
        return None


async def request_approval_with_files(
    agent,
    request_id: str,
    message: str,
    files: list[str],
    timeout_seconds: int = 3600,
) -> Optional[bool]:
    """Запрашивает одобрение и отправляет файлы-превью до запроса."""
    sent_any = False
    for fp in files:
        try:
            await agent.send_file(fp, caption=f"Превью: {Path(fp).name}")
            sent_any = True
        except Exception:
            continue
    if not sent_any and files:
        message = message + "\n(ВНИМАНИЕ: файлы превью не отправлены.)"
    return await request_approval(agent, request_id=request_id, message=message, timeout_seconds=timeout_seconds)


def pending_approvals_count(agent) -> int:
    return len(agent._pending_approvals or {})


def pending_approvals_list(agent) -> list[str]:
    try:
        return list(agent._pending_approvals.keys())
    except Exception:
        return []
