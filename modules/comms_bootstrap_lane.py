from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from config.logger import get_logger
from config.settings import settings
from modules.auth_broker import AuthBroker
from modules.comms_broadcast_queue import BroadcastQueue
from modules.comms_notification_router import NotificationRouter

logger = get_logger("comms_agent", agent="comms_agent")


def build_button_map() -> dict[str, str]:
    return {
        "Главная": "start",
        "Статус": "status",
        "Задачи": "tasks",
        "В работе": "tasks",
        "Исследовать": "research_hub",
        "Создать": "create_hub",
        "Платформы": "platforms_hub",
        "Входы": "auth_hub",
        "Сводка": "report",
        "Отчёт": "report",
        "Еще": "more",
        "Ещё": "more",
        "Цели": "goals",
        "Расходы": "spend",
        "Одобрить": "approve",
        "Отклонить": "reject",
        "Новая цель": "goal",
        "Помощь": "help",
        "Ежедневные": "help_daily",
        "Редкие": "help_rare",
        "Системные": "help_system",
    }


def init_runtime_state(agent: Any, install_reply_trace_patch, load_auth_state) -> None:
    try:
        agent._owner_id = int(str(getattr(settings, "TELEGRAM_OWNER_CHAT_ID", "") or "0").strip())
    except Exception:
        agent._owner_id = 0
    agent._notify_mode = getattr(settings, "NOTIFY_MODE", "minimal")

    agent._pending_approvals = {}
    agent._approval_last_sent_at = {}
    agent._pending_schedule_update = None
    agent._pending_system_action = None
    agent._pending_owner_confirmation = None
    agent._pending_choice_context = None
    agent._pending_kdp_otp = None
    agent._kdp_auth_lock = asyncio.Lock()
    agent._pending_service_auth = {}
    agent._service_auth_confirmed = {}
    agent._last_service_context = ""
    agent._last_service_context_at = ""
    agent._auth_state_path = Path(
        str(getattr(settings, "TELEGRAM_AUTH_STATE_FILE", "runtime/service_auth_state.json") or "runtime/service_auth_state.json")
    )
    agent._auth_broker = AuthBroker(
        state_path=str(getattr(settings, "AUTH_BROKER_STATE_FILE", "runtime/auth_broker_state.json"))
    )
    load_auth_state()
    agent._telegram_conflict_mode = False
    agent._telegram_trace_path = Path(
        str(getattr(settings, "TELEGRAM_TRACE_FILE", "runtime/telegram_trace.jsonl") or "runtime/telegram_trace.jsonl")
    )
    install_reply_trace_patch(agent._telegram_trace_path)
    agent._logger = logger
    agent._broadcast_queue = BroadcastQueue()
    agent._notification_router = NotificationRouter(agent, agent._broadcast_queue)

    agent._goal_engine = None
    agent._llm_router = None
    agent._decision_loop = None
    agent._agent_registry = None
    agent._self_healer = None
    agent._self_updater = None
    agent._conversation_engine = None
    agent._judge_protocol = None
    agent._finance = None
    agent._skill_registry = None
    agent._weekly_planner = None
    agent._schedule_manager = None
    agent._publisher_queue = None
    agent._cancel_state = None
    agent._owner_task_state = None

    agent._button_map = build_button_map()
    logger.info("CommsAgent инициализирован", extra={"event": "init"})


def approval_channel(request_id: str) -> str:
    rid = str(request_id or "").strip().lower()
    if rid.startswith("publish_"):
        parts = rid.split("_")
        if len(parts) >= 2:
            return f"publish_{parts[1]}"
    return ""


def append_telegram_trace(agent: Any, append_file, direction: str, text: str, meta: dict[str, Any] | None = None) -> None:
    append_file(agent._telegram_trace_path, direction, text, meta)


def resolve_button_command(button_map: dict[str, str], text: str) -> str | None:
    s = str(text or "").strip()
    cmd = button_map.get(s)
    if cmd:
        return cmd
    normalized = s.lstrip("📊📈📉📌📎✅❌⚙️⚙🔥⭐️⭐🔐🔑🧠📚🧾💸💰🚀 ").strip()
    return button_map.get(normalized)


def is_confirmed(args: list[str] | None) -> bool:
    if not args:
        return False
    token = str(args[0] or "").strip().lower()
    return token in {"yes", "y", "да", "confirm", "ok"}


def autonomy_max_enabled() -> bool:
    return bool(getattr(settings, "AUTONOMY_MAX_MODE", False))


def parse_bool_env(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_yes_token(text: str) -> bool:
    return str(text or "").strip().lower() in {"да", "yes", "ок", "ok", "approve", "✅", "👍"}


def is_no_token(text: str) -> bool:
    return str(text or "").strip().lower() in {"нет", "no", "reject", "отмена", "❌", "👎"}
