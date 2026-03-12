from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from telegram import Update

from config.logger import get_logger
from config.paths import root_path
from config.settings import settings

logger = get_logger(__name__)


def set_env_values(agent: Any, updates: dict[str, str]) -> bool:
    if not updates:
        return False
    env_path = Path(root_path(".env"))
    text_env = env_path.read_text() if env_path.exists() else ""
    for key, value in updates.items():
        k = str(key or "").strip().upper()
        v = str(value or "").strip()
        if not k:
            continue
        if re.search(rf"^{re.escape(k)}=.*$", text_env, flags=re.M):
            text_env = re.sub(rf"^{re.escape(k)}=.*$", f"{k}={v}", text_env, flags=re.M)
        else:
            if text_env and not text_env.endswith("\n"):
                text_env += "\n"
            text_env += f"{k}={v}\n"
        os.environ[k] = v
        try:
            if hasattr(settings, k):
                cur = getattr(settings, k)
                if isinstance(cur, bool):
                    setattr(settings, k, agent._parse_bool_env(v))
                elif isinstance(cur, int):
                    try:
                        setattr(settings, k, int(v))
                    except Exception:
                        setattr(settings, k, v)
                elif isinstance(cur, float):
                    try:
                        setattr(settings, k, float(v))
                    except Exception:
                        setattr(settings, k, v)
                else:
                    setattr(settings, k, v)
        except Exception:
            pass
    env_path.write_text(text_env)
    return True


def try_set_env_from_text(agent: Any, text: str) -> bool:
    m = re.search(r"(?:^|\\bset\\s+)([A-Z0-9_]{3,})\\s*=\\s*([^\\s]+)", text, re.IGNORECASE)
    if not m:
        return False
    key = m.group(1).upper()
    value = m.group(2).strip()
    allowed = {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "PERPLEXITY_API_KEY",
        "OPENROUTER_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_OWNER_CHAT_ID",
        "GUMROAD_API_KEY",
        "GUMROAD_OAUTH_TOKEN",
        "GUMROAD_APP_ID",
        "GUMROAD_APP_SECRET",
        "ETSY_KEYSTRING",
        "ETSY_SHARED_SECRET",
        "ETSY_EMAIL",
        "ETSY_PASSWORD",
        "KOFI_API_KEY",
        "KOFI_PAGE_ID",
        "REPLICATE_API_TOKEN",
        "ANTICAPTCHA_KEY",
        "TWITTER_BEARER_TOKEN",
        "TWITTER_CONSUMER_KEY",
        "TWITTER_CONSUMER_SECRET",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_SECRET",
        "THREADS_ACCESS_TOKEN",
        "THREADS_USER_ID",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USERNAME",
        "REDDIT_PASSWORD",
        "REDDIT_USER_AGENT",
        "TIKTOK_ACCESS_TOKEN",
    }
    if key not in allowed:
        return False
    set_env_values(agent, {key: value})
    logger.info("Env key set via Telegram", extra={"event": "env_set", "context": {"key": key}})
    return True


def apply_llm_mode(agent: Any, mode: str) -> tuple[bool, str]:
    m = str(mode or "").strip().lower()
    if m in {"free", "test", "gemini", "flash"}:
        set_env_values(
            agent,
            {
                "LLM_ROUTER_MODE": "free",
                "LLM_FORCE_GEMINI_FREE": "true",
                "LLM_FORCE_GEMINI_MODEL": "gemini-2.5-flash",
                "LLM_ENABLED_MODELS": "gemini-2.5-flash",
                "LLM_DISABLED_MODELS": "claude-haiku-4-5-20251001,gpt-4o-mini,claude-sonnet-4-6,o3,gpt-4o-strategic,claude-opus-4-6,sonar-pro",
                "GEMINI_ENABLE_GROUNDING_SEARCH": "true",
                "GEMINI_ENABLE_URL_CONTEXT": "true",
                "GEMINI_EMBEDDINGS_ENABLED": "true",
                "GEMINI_EMBED_MODEL": "gemini-embedding-001",
                "GEMINI_ENABLE_IMAGEN": "true",
                "GEMINI_LIVE_API_ENABLED": "true",
                "IMAGE_ROUTER_PREFER_GEMINI": "true",
                "GEMINI_FREE_MAX_RPM": "15",
                "GEMINI_FREE_TEXT_RPD": "1000",
                "GEMINI_FREE_SEARCH_RPD": "1500",
                "MODEL_ACTIVE_PROFILE": "gemini_free",
            },
        )
        return True, (
            "LLM режим: FREE (тест)\n"
            "- Все задачи идут через Gemini 2.5 Flash\n"
            "- Платные модели отключены\n"
            "- Grounding Search + URL Context включены\n"
            "- Embeddings + Imagen + Live API включены (если есть доступ)\n"
            "- Перезапуск не обязателен, но желателен для чистого цикла"
        )
    if m in {"prod", "production", "battle", "боевой"}:
        set_env_values(
            agent,
            {
                "LLM_ROUTER_MODE": "prod",
                "LLM_FORCE_GEMINI_FREE": "false",
                "LLM_FORCE_GEMINI_MODEL": "gemini-2.5-flash",
                "LLM_ENABLED_MODELS": "",
                "LLM_DISABLED_MODELS": "",
                "IMAGE_ROUTER_PREFER_GEMINI": "false",
                "MODEL_ACTIVE_PROFILE": "balanced",
            },
        )
        return True, (
            "LLM режим: PROD (боевой)\n"
            "- ROUTINE: Gemini -> 4o-mini -> Haiku\n"
            "- CONTENT: Sonnet -> Haiku -> Gemini\n"
            "- CODE/SELF_HEAL: o3 -> Sonnet -> GPT-5\n"
            "- RESEARCH: Perplexity -> Gemini -> Sonnet\n"
            "- STRATEGY: Opus -> GPT-5 -> Sonnet"
        )
    if m in {"status", "show", "current", "текущий"}:
        free = bool(getattr(settings, "LLM_FORCE_GEMINI_FREE", False))
        enabled = str(getattr(settings, "LLM_ENABLED_MODELS", "") or "")
        disabled = str(getattr(settings, "LLM_DISABLED_MODELS", "") or "")
        model = str(getattr(settings, "LLM_FORCE_GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash")
        mode_val = str(getattr(settings, "LLM_ROUTER_MODE", "prod") or "prod")
        embed = bool(getattr(settings, "GEMINI_EMBEDDINGS_ENABLED", False))
        img = bool(getattr(settings, "GEMINI_ENABLE_IMAGEN", False))
        live = bool(getattr(settings, "GEMINI_LIVE_API_ENABLED", False))
        mode_name = "FREE (Gemini-only)" if free else "PROD (task-based)"
        return True, (
            f"LLM режим сейчас: {mode_name}\n"
            f"LLM_ROUTER_MODE={mode_val}\n"
            f"LLM_FORCE_GEMINI_MODEL={model}\n"
            f"GEMINI_EMBEDDINGS_ENABLED={str(embed).lower()} | GEMINI_ENABLE_IMAGEN={str(img).lower()} | GEMINI_LIVE_API_ENABLED={str(live).lower()}\n"
            f"LLM_ENABLED_MODELS={enabled or '(empty)'}\n"
            f"LLM_DISABLED_MODELS={disabled or '(empty)'}"
        )
    return False, "Использование: /llm_mode free | /llm_mode prod | /llm_mode status"


async def execute_pending_system_action(agent: Any, update: Update | None = None) -> None:
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


def schedule_system_actions_background(
    agent: Any,
    actions: list[dict[str, Any]],
    *,
    update: Update | None = None,
    origin_text: str = "",
) -> None:
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


async def on_app_error(agent: Any, update: object, context: Any) -> None:
    try:
        raise context.error
    except Exception:
        logger.exception("Telegram application error", extra={"event": "telegram_app_error"})
