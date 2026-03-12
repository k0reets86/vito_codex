from __future__ import annotations

import asyncio
from typing import Any

from telegram import Update

from config.logger import get_logger

logger = get_logger("comms_owner_runtime_lane")


async def maybe_handle_owner_service_commands(agent, text: str) -> bool:
    service_status = agent._detect_contextual_service_status_request(text)
    if service_status:
        await agent.send_message(await agent._format_service_auth_status_live(service_status), level="result")
        return True
    service_inventory = agent._detect_contextual_service_inventory_request(text)
    if service_inventory:
        await agent.send_message(await agent._format_service_inventory_snapshot(service_inventory), level="result")
        agent._record_context_learning(
            skill_name="contextual_service_inventory_resolution",
            description=(
                "Если активен контекст платформы, запросы вида 'проверь товары/листинги' выполняются как проверка аккаунта этой платформы, а не как market research."
            ),
            anti_pattern=(
                "Плохо: отправлять владельца в analyze_niche, когда он просит проверить товары в текущем аккаунте."
            ),
            method={"service": service_inventory, "source_text": text[:120]},
        )
        return True
    return False


async def execute_pending_system_action(agent, update: Update | None = None) -> None:
    payload = agent._pending_system_action or {}
    agent._pending_system_action = None
    actions = payload.get("actions") or []
    if not actions:
        if update is not None:
            await update.message.reply_text("Нет действий для выполнения.", reply_markup=agent._main_keyboard())
        else:
            await agent.send_message("Нет действий для выполнения.", level="result")
        return
    if not agent._conversation_engine:
        if update is not None:
            await update.message.reply_text("ConversationEngine не подключён.", reply_markup=agent._main_keyboard())
        else:
            await agent.send_message("ConversationEngine не подключён.", level="result")
        return
    try:
        out = await agent._conversation_engine._execute_actions(actions)
        msg = out or "Действие выполнено."
    except Exception as e:
        msg = f"Ошибка выполнения действия: {e}"
    if update is not None:
        await agent._send_response(update, msg)
    else:
        await agent.send_message(msg, level="result")


def schedule_system_actions_background(agent, actions: list[dict[str, Any]], *, update: Update | None = None, origin_text: str = "") -> None:
    if not actions or not agent._conversation_engine:
        return

    async def _runner() -> None:
        try:
            out = await agent._conversation_engine._execute_actions(actions)
            msg = out or "Действие выполнено."
        except Exception as e:
            msg = f"Ошибка выполнения действия: {e}"
        try:
            if update is not None:
                await agent._send_response(update, msg)
            else:
                await agent.send_message(msg, level="result")
        except Exception:
            logger.exception(
                "Background system action follow-up failed",
                extra={
                    "event": "background_system_action_followup_failed",
                    "context": {"origin_text": origin_text[:200], "actions_count": len(actions)},
                },
            )

    task = asyncio.create_task(_runner())
    logger.info(
        "Scheduled background system actions",
        extra={
            "event": "background_system_actions_scheduled",
            "context": {"origin_text": origin_text[:200], "actions_count": len(actions), "task_id": id(task)},
        },
    )
