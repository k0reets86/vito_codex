from __future__ import annotations

import re
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from modules.comms_message_preflight_lane import (
    handle_contextual_service_prompts as _handle_contextual_service_prompts_impl,
    handle_pending_owner_confirmation as _handle_pending_owner_confirmation_impl,
    handle_pending_schedule_update as _handle_pending_schedule_update_impl,
    handle_pending_service_auth as _handle_pending_service_auth_impl,
    handle_pending_system_action as _handle_pending_system_action_impl,
)
from modules.comms_message_route_lane import (
    handle_deterministic_message_routes as _handle_deterministic_message_routes_impl,
)


def extract_reply_context(update: Update) -> dict[str, str]:
    """Extract replied message payload from Telegram swipe-reply."""
    try:
        msg = getattr(update, "message", None)
        if msg is None:
            return {}
        parent = getattr(msg, "reply_to_message", None)
        if parent is None:
            return {}
        parent_text = getattr(parent, "text", None) or getattr(parent, "caption", None) or ""
        if not isinstance(parent_text, str):
            return {}
        parent_text = parent_text.strip()
        if not parent_text:
            return {}
        message_id = getattr(parent, "message_id", "")
        return {"message_id": str(message_id or ""), "text": parent_text[:1200]}
    except Exception:
        return {}


def has_numbered_options(text: str) -> bool:
    lines = re.findall(r"(?m)^\s*(\d{1,2})[\.\)]\s+\S+", str(text or ""))
    return len(lines) >= 2


def remember_choice_context(agent, response_text: str) -> None:
    if has_numbered_options(response_text):
        agent._pending_choice_context = {"saved_at": datetime.now(timezone.utc).isoformat()}


def expand_short_choice(agent, raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text.isdigit():
        return text
    if not agent._pending_choice_context:
        return text
    idx = int(text)
    if idx <= 0:
        return text
    agent._pending_choice_context = None
    return f"Вариант {idx}. Зафиксируй выбор и жди следующую команду."


def decorate_with_numeric_hint(response: str, actions: list[dict] | None) -> str:
    text = str(response or "").strip()
    return text


def owner_goal_response_override(agent, source_text: str, default_response: str, goal_title: str) -> str:
    text = str(source_text or "").strip().lower()
    response = str(default_response or "").strip()
    goal = str(goal_title or "").strip()
    platform = ""
    try:
        platform = str(agent._extract_platform_key(source_text) or "").strip().lower()
    except Exception:
        platform = ""
    if platform and any(tok in text for tok in ("создавай", "сделай", "запускай", "публикуй")):
        return f"Собираю и запускаю работу на {platform}: {goal or response}."
    return response


def normalize_owner_control_reply(agent, source_text: str, response_text: str) -> str:
    src = str(source_text or "").strip().lower()
    out = str(response_text or "").strip()
    low_out = out.lower()
    if src.isdigit():
        if "зафиксировал вариант" in low_out:
            return out
        idx = int(src)
        return f"Зафиксировал вариант {idx}. Жду следующую команду."
    platform = ""
    try:
        platform = str(agent._extract_platform_key(source_text) or "").strip().lower()
    except Exception:
        platform = ""
    if platform and any(tok in src for tok in ("создавай", "сделай", "запускай", "публикуй")):
        if "собираю" in low_out and platform in low_out:
            return out
        return f"Собираю и запускаю работу на {platform}."
    if any(tok in src for tok in ("соц", "social", "соцпакет")) and any(tok in low_out for tok in ("x", "pinterest", "соц")):
        return out
    return out


async def on_message(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Произвольное текстовое сообщение от владельца → ConversationEngine."""
    if await agent._reject_stranger(update):
        return

    text = update.message.text.strip()
    if not text:
        return

    agent._append_telegram_trace("in", text, {"chat_id": int(agent._owner_id)})

    reply_meta = extract_reply_context(update)
    reply_service = agent._detect_service_from_reply_context(reply_meta)
    if reply_service:
        agent._touch_service_context(reply_service)
    source = "text_reply" if reply_meta else "text"

    agent._log_owner_request(text, source=source)
    strict_cmds = bool(getattr(settings, "TELEGRAM_STRICT_COMMANDS", True)) and not agent._autonomy_max_enabled()

    async def _tg_reply(msg: str, markup=None) -> None:
        kwargs = {"reply_markup": markup} if markup is not None else {"reply_markup": agent._main_keyboard()}
        await update.message.reply_text(msg, **kwargs)

    login_svc = agent._detect_service_login_request(text)
    if login_svc and agent._is_inventory_prompt(text):
        agent._touch_service_context(login_svc)
        if agent._service_auth_confirmed.get(login_svc):
            await update.message.reply_text(
                await agent._format_service_inventory_snapshot(login_svc),
                reply_markup=agent._main_keyboard(),
            )
            return
    if await agent._handle_kdp_login_flow(text, _tg_reply, with_button=True):
        agent._touch_service_context("amazon_kdp")
        return
    svc = login_svc
    if svc and svc != "amazon_kdp":
        if await agent._start_service_auth_flow(svc, _tg_reply, with_button=True):
            return

    lower = text.lower()
    if await _handle_pending_service_auth_impl(agent, update, lower):
        return

    if await _handle_contextual_service_prompts_impl(agent, update, text):
        return

    lower = text.lower()
    if await _handle_pending_service_auth_impl(agent, update, lower):
        return
    if await _handle_pending_owner_confirmation_impl(agent, update, lower):
        return
    if await _handle_pending_system_action_impl(agent, update, text, lower, strict_cmds):
        return
    if await _handle_pending_schedule_update_impl(agent, update, text):
        return

    if text.isdigit() and agent._prime_research_pending_actions_from_owner_state(text):
        idx = int(text)
        picked = agent._select_pending_research_option(idx)
        if picked is not None:
            title = str(picked.get("title") or "").strip()
            score = int(picked.get("score", 0) or 0)
            await update.message.reply_text(
                (
                    f"Зафиксировал вариант {idx}: {title} ({score}/100). "
                    "Если запускать сразу, напиши: «создавай» или укажи платформу."
                ),
                reply_markup=agent._main_keyboard(),
            )
            return

    if not strict_cmds:
        text = expand_short_choice(agent, text)
        lower = text.lower()

    if (not strict_cmds) and any(kw in lower for kw in [
        "очисти очередь",
        "очисти очередь целей",
        "удали все цели",
        "удали цели",
        "очисти цели",
        "сними все цели",
        "убери все цели",
        "delete all goals",
    ]):
        agent._pending_owner_confirmation = {"kind": "clear_goals", "created_at": datetime.now(timezone.utc).isoformat()}
        await update.message.reply_text(
            "Подтверди очистку всех целей: да/нет",
            reply_markup=agent._main_keyboard(),
        )
        return

    if (not strict_cmds) and await agent._maybe_schedule_from_text(update, text):
        return

    if (not strict_cmds) and await agent._maybe_brainstorm_from_text(update, text):
        return

    if agent._try_set_env_from_text(text):
        await update.message.reply_text(
            "Ключ принят и сохранён. Если нужен перезапуск сервиса — скажи 'перезапусти'.",
            reply_markup=agent._main_keyboard(),
        )
        return

    if await _handle_deterministic_message_routes_impl(agent, update, context, text, strict_cmds=strict_cmds):
        return

    async def _tg_reply2(msg: str, reply_markup=None):
        await update.message.reply_text(msg, reply_markup=reply_markup or agent._main_keyboard())

    if await agent._handle_kdp_login_flow(text, _tg_reply2, with_button=True):
        return

    text_for_engine = text
    if reply_meta:
        text_for_engine = (
            f"[REPLY_CONTEXT]\n"
            f"reply_to_message_id={reply_meta.get('message_id','')}\n"
            f"reply_to_text={reply_meta.get('text','')}\n"
            f"owner_reply={text}\n"
            f"[/REPLY_CONTEXT]"
        )

    if agent._conversation_engine:
        try:
            if hasattr(agent._conversation_engine, "set_session"):
                sid = str(update.effective_chat.id) if update and update.effective_chat else "telegram_owner"
                agent._conversation_engine.set_session(sid)
            if hasattr(agent._conversation_engine, "set_defer_owner_actions"):
                agent._conversation_engine.set_defer_owner_actions(True)
            result = await agent._conversation_engine.process_message(text_for_engine)

            if result.get("pass_through"):
                pass
            elif result.get("create_goal") and agent._goal_engine:
                from goal_engine import GoalPriority, GoalStatus

                priority_map = {
                    "CRITICAL": GoalPriority.CRITICAL,
                    "HIGH": GoalPriority.HIGH,
                    "MEDIUM": GoalPriority.MEDIUM,
                    "LOW": GoalPriority.LOW,
                }
                goal = agent._goal_engine.create_goal(
                    title=result.get("goal_title", text[:100]),
                    description=result.get("goal_description", text),
                    priority=priority_map.get(result.get("goal_priority", "HIGH"), GoalPriority.HIGH),
                    source="owner",
                    estimated_cost_usd=result.get("estimated_cost_usd", 0.05),
                )
                if result.get("needs_approval", False):
                    goal.status = GoalStatus.WAITING_APPROVAL
                    agent._goal_engine._persist_goal(goal)
                response = result.get("response", f"Цель создана: {goal.title}")
                response = owner_goal_response_override(agent, text_for_engine, response, goal.title)
                if result.get("needs_approval"):
                    response += "\n\nПодтверди запуск: да/нет."
                response = decorate_with_numeric_hint(response, result.get("actions", []))
                response = normalize_owner_control_reply(agent, text_for_engine, response)
                response = agent._humanize_owner_text(response)
                remember_choice_context(agent, response)
                await update.message.reply_text(response, reply_markup=agent._main_keyboard())
            elif result.get("response"):
                response = decorate_with_numeric_hint(result["response"], result.get("actions", []))
                response = normalize_owner_control_reply(agent, text_for_engine, response)
                remember_choice_context(agent, response)
                await agent._send_response(update, response)
                agent._prime_research_pending_actions_from_owner_state(text_for_engine)
                if result.get("actions") and result.get("needs_confirmation"):
                    if agent._autonomy_max_enabled() and agent._conversation_engine:
                        out = await agent._conversation_engine._execute_actions(result.get("actions", []))
                        await agent._send_response(update, out or "Действие выполнено.")
                    else:
                        agent._pending_system_action = {
                            "actions": result.get("actions", []),
                            "origin_text": text_for_engine,
                        }
                elif result.get("actions"):
                    agent._schedule_system_actions_background(
                        result.get("actions", []),
                        update=update,
                        origin_text=text_for_engine,
                    )
            else:
                await update.message.reply_text(
                    "Понял. Чем могу помочь?", reply_markup=agent._main_keyboard()
                )

            agent._logger.info(
                f"ConversationEngine: intent={result.get('intent')}",
                extra={"event": "conversation_processed", "context": {"intent": result.get("intent")}},
            )
            return
        except Exception as e:
            agent._logger.warning(f"ConversationEngine error: {e}", extra={"event": "conversation_error"})

    await update.message.reply_text(
        "Не понял: это вопрос или задача? Напиши одним предложением, что нужно сделать.",
        reply_markup=agent._main_keyboard(),
    )
    agent._logger.info(
        f"Сообщение от владельца: {text[:100]}",
        extra={"event": "owner_message"},
    )
