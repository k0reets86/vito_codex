from __future__ import annotations

import asyncio
import os
import re
from typing import Any


def set_env_values(settings_obj, root_path_fn, updates: dict[str, str]) -> bool:
    if not updates:
        return False
    env_path = root_path_fn('.env')
    from pathlib import Path
    env_path = Path(env_path)
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
            if hasattr(settings_obj, k):
                cur = getattr(settings_obj, k)
                if isinstance(cur, bool):
                    setattr(settings_obj, k, str(v).strip().lower() in {"1", "true", "yes", "on"})
                elif isinstance(cur, int):
                    try:
                        setattr(settings_obj, k, int(v))
                    except Exception:
                        setattr(settings_obj, k, v)
                elif isinstance(cur, float):
                    try:
                        setattr(settings_obj, k, float(v))
                    except Exception:
                        setattr(settings_obj, k, v)
                else:
                    setattr(settings_obj, k, v)
        except Exception:
            pass
    env_path.write_text(text_env)
    return True


def try_set_env_from_text(agent, logger_obj, text: str) -> bool:
    m = re.search(r"(?:^|\bset\s+)([A-Z0-9_]{3,})\s*=\s*([^\s]+)", text, re.IGNORECASE)
    if not m:
        return False
    key = m.group(1).upper()
    value = m.group(2).strip()
    allowed = {
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
        "PERPLEXITY_API_KEY", "OPENROUTER_API_KEY",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID",
        "GUMROAD_API_KEY", "GUMROAD_OAUTH_TOKEN", "GUMROAD_APP_ID", "GUMROAD_APP_SECRET",
        "ETSY_KEYSTRING", "ETSY_SHARED_SECRET", "ETSY_EMAIL", "ETSY_PASSWORD", "KOFI_API_KEY", "KOFI_PAGE_ID",
        "REPLICATE_API_TOKEN", "ANTICAPTCHA_KEY",
        "TWITTER_BEARER_TOKEN", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET",
        "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
        "THREADS_ACCESS_TOKEN", "THREADS_USER_ID",
        "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD", "REDDIT_USER_AGENT",
        "TIKTOK_ACCESS_TOKEN",
    }
    if key not in allowed:
        return False
    agent._set_env_values({key: value})
    logger_obj.info("Env key set via Telegram", extra={"event": "env_set", "context": {"key": key}})
    return True


def apply_llm_mode(agent, settings_obj, mode: str) -> tuple[bool, str]:
    m = str(mode or "").strip().lower()
    if m in {"free", "test", "gemini", "flash"}:
        agent._set_env_values(
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
            }
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
        agent._set_env_values(
            {
                "LLM_ROUTER_MODE": "prod",
                "LLM_FORCE_GEMINI_FREE": "false",
                "LLM_FORCE_GEMINI_MODEL": "gemini-2.5-flash",
                "LLM_ENABLED_MODELS": "",
                "LLM_DISABLED_MODELS": "",
                "IMAGE_ROUTER_PREFER_GEMINI": "false",
                "MODEL_ACTIVE_PROFILE": "balanced",
            }
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
        free = bool(getattr(settings_obj, "LLM_FORCE_GEMINI_FREE", False))
        enabled = str(getattr(settings_obj, "LLM_ENABLED_MODELS", "") or "")
        disabled = str(getattr(settings_obj, "LLM_DISABLED_MODELS", "") or "")
        model = str(getattr(settings_obj, "LLM_FORCE_GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash")
        router_mode = str(getattr(settings_obj, "LLM_ROUTER_MODE", "prod") or "prod")
        embed = bool(getattr(settings_obj, "GEMINI_EMBEDDINGS_ENABLED", False))
        img = bool(getattr(settings_obj, "GEMINI_ENABLE_IMAGEN", False))
        live = bool(getattr(settings_obj, "GEMINI_LIVE_API_ENABLED", False))
        mode_name = "FREE (Gemini-only)" if free else "PROD (task-based)"
        return True, (
            f"LLM режим сейчас: {mode_name}\n"
            f"LLM_ROUTER_MODE={router_mode}\n"
            f"LLM_FORCE_GEMINI_MODEL={model}\n"
            f"GEMINI_EMBEDDINGS_ENABLED={str(embed).lower()} | GEMINI_ENABLE_IMAGEN={str(img).lower()} | GEMINI_LIVE_API_ENABLED={str(live).lower()}\n"
            f"LLM_ENABLED_MODELS={enabled or '(empty)'}\n"
            f"LLM_DISABLED_MODELS={disabled or '(empty)'}"
        )
    return False, "Использование: /llm_mode free | /llm_mode prod | /llm_mode status"


async def execute_pending_system_action(agent, update=None) -> None:
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


def schedule_system_actions_background(agent, logger_obj, actions: list[dict[str, Any]], *, update=None, origin_text: str = "") -> None:
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
            logger_obj.exception(
                "Background system action follow-up failed",
                extra={
                    "event": "background_system_action_followup_failed",
                    "context": {"origin_text": origin_text[:200], "actions_count": len(actions)},
                },
            )

    task = asyncio.create_task(_runner())
    logger_obj.info(
        "Scheduled background system actions",
        extra={
            "event": "background_system_actions_scheduled",
            "context": {"origin_text": origin_text[:200], "actions_count": len(actions), "task_id": id(task)},
        },
    )


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


def auto_detect_preference(owner_preference_model_cls, text: str) -> None:
    raw = (text or "").strip()
    lower = raw.lower()
    if "пиши кратко" in lower or lower == "кратко":
        owner_preference_model_cls().record_signal(
            key="style.verbosity", value="concise", signal_type="observation", source="owner", confidence_delta=0.1, notes="auto_detect"
        )
    if "пиши подробно" in lower or "подробно" == lower:
        owner_preference_model_cls().record_signal(
            key="style.verbosity", value="verbose", signal_type="observation", source="owner", confidence_delta=0.1, notes="auto_detect"
        )
    if "на английском" in lower or "по-английски" in lower or "english only" in lower:
        owner_preference_model_cls().record_signal(
            key="content.language", value="en", signal_type="observation", source="owner", confidence_delta=0.08, notes="auto_detect"
        )
    if "на русском" in lower or "по-русски" in lower:
        owner_preference_model_cls().record_signal(
            key="content.language", value="ru", signal_type="observation", source="owner", confidence_delta=0.08, notes="auto_detect"
        )
    if "сначала тесты" in lower or "после тестов" in lower:
        owner_preference_model_cls().record_signal(
            key="workflow.tests_first", value=True, signal_type="observation", source="owner", confidence_delta=0.08, notes="auto_detect"
        )
