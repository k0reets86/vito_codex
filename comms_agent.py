"""Comms Agent — Telegram-бот для связи VITO с владельцем.

Двусторонняя коммуникация:
  Владелец → VITO: команды, одобрения, задачи
  VITO → Владелец: отчёты, запросы одобрения, уведомления

Команды (Owner Protocol v5.0):
  /status  — текущий статус системы
  /goals   — список активных целей
  /spend   — расходы за сегодня
  /approve — одобрить ожидающий запрос
  /reject  — отклонить ожидающий запрос
  /goal    — создать новую цель

Безопасность: отвечает ТОЛЬКО владельцу (TELEGRAM_OWNER_CHAT_ID).
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from telegram import (
    Bot,
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest as TgBadRequest
from telegram.error import Conflict as TgConflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.logger import get_logger
from config.paths import PROJECT_ROOT, root_path
from config.settings import settings
from modules.owner_preference_model import OwnerPreferenceModel
from modules.owner_pref_metrics import OwnerPreferenceMetrics
from modules.data_lake import DataLake
from modules.status_snapshot import build_status_snapshot, render_status_snapshot

logger = get_logger("comms_agent", agent="comms_agent")

_TELEGRAM_TRACE_DEFAULT = root_path("runtime/telegram_trace.jsonl")


def _append_telegram_trace_file(path: Path, direction: str, text: str, meta: dict[str, Any] | None = None) -> None:
    """Write one Telegram trace line (best-effort, no exceptions)."""
    try:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": str(direction or "").strip().lower(),
            "text": str(text or ""),
            "meta": dict(meta or {}),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _install_reply_text_trace_patch(path: Path) -> None:
    """Patch telegram.Message.reply_text once to mirror bot replies into trace file."""
    try:
        from telegram import Message as TgMessage  # lazy import for safety

        if bool(getattr(TgMessage, "_vito_reply_trace_patched", False)):
            return
        original = TgMessage.reply_text

        async def _traced_reply_text(self, *args, **kwargs):  # type: ignore[override]
            text = ""
            if args:
                text = str(args[0] or "")
            elif "text" in kwargs:
                text = str(kwargs.get("text") or "")
            _append_telegram_trace_file(
                path,
                "out",
                text,
                {
                    "chat_id": int(getattr(self, "chat_id", 0) or 0),
                    "level": "reply",
                },
            )
            return await original(self, *args, **kwargs)

        TgMessage.reply_text = _traced_reply_text  # type: ignore[assignment]
        setattr(TgMessage, "_vito_reply_trace_patched", True)
    except Exception:
        pass


class CommsAgent:
    _SERVICE_CATALOG: dict[str, dict[str, Any]] = {
        "amazon_kdp": {
            "title": "Amazon KDP",
            "url": "https://kdp.amazon.com",
            "aliases": ("amazon", "амазон", "kdp", "кдп", "amazon kdp", "amazon books"),
            "manual_fallback": True,
        },
        "etsy": {
            "title": "Etsy",
            "url": "https://www.etsy.com/signin",
            "aliases": ("etsy", "етси", "этси"),
            "manual_fallback": True,
        },
        "gumroad": {
            "title": "Gumroad",
            "url": "https://gumroad.com/login",
            "aliases": ("gumroad", "гумроад", "гамроад"),
            "manual_fallback": True,
        },
        "printful": {
            "title": "Printful",
            "url": "https://www.printful.com/dashboard",
            "aliases": ("printful", "принтфул"),
            "manual_fallback": True,
        },
        "kofi": {
            "title": "Ko-fi",
            "url": "https://ko-fi.com/manage",
            "aliases": ("kofi", "ko-fi", "кофи", "ко-фи"),
            "manual_fallback": True,
        },
        "twitter": {
            "title": "X (Twitter)",
            "url": "https://x.com/i/flow/login",
            "aliases": ("twitter", "x.com", " x ", "твиттер", "твитер", "икс"),
            "manual_fallback": True,
        },
        "reddit": {
            "title": "Reddit",
            "url": "https://www.reddit.com/login/",
            "aliases": ("reddit", "реддит"),
            "manual_fallback": True,
        },
        "threads": {
            "title": "Threads",
            "url": "https://www.threads.net/login",
            "aliases": ("threads", "тредс", "тридс"),
            "manual_fallback": True,
        },
        "instagram": {
            "title": "Instagram",
            "url": "https://www.instagram.com/accounts/login/",
            "aliases": ("instagram", "insta", "инстаграм", "инста"),
            "manual_fallback": True,
        },
        "facebook": {
            "title": "Facebook",
            "url": "https://www.facebook.com/login",
            "aliases": ("facebook", "fb", "фейсбук", "фб"),
            "manual_fallback": True,
        },
        "tiktok": {
            "title": "TikTok",
            "url": "https://www.tiktok.com/login",
            "aliases": ("tiktok", "tik tok", "тикток", "тикток"),
            "manual_fallback": True,
        },
        "pinterest": {
            "title": "Pinterest",
            "url": "https://www.pinterest.com/login/",
            "aliases": ("pinterest", "пинтерест"),
            "manual_fallback": True,
        },
        "youtube": {
            "title": "YouTube Studio",
            "url": "https://studio.youtube.com/",
            "aliases": ("youtube", "ютуб", "ютьюб", "youtube studio"),
            "manual_fallback": True,
        },
        "linkedin": {
            "title": "LinkedIn",
            "url": "https://www.linkedin.com/login",
            "aliases": ("linkedin", "линкедин", "линкед ин"),
            "manual_fallback": True,
        },
        "wordpress": {
            "title": "WordPress",
            "url": "https://wordpress.com/log-in",
            "aliases": ("wordpress", "вордпресс", "wp"),
            "manual_fallback": True,
        },
        "medium": {
            "title": "Medium",
            "url": "https://medium.com/m/signin",
            "aliases": ("medium", "медиум"),
            "manual_fallback": True,
        },
    }
    _SITE_ALIAS_URLS: dict[str, str] = {
        "укр нет": "ukr.net",
        "укрнет": "ukr.net",
        "ukr net": "ukr.net",
        "ukrnet": "ukr.net",
        "укр правда": "www.pravda.com.ua",
        "укрправда": "www.pravda.com.ua",
        "укр правду": "www.pravda.com.ua",
        "укрправду": "www.pravda.com.ua",
        "украинская правда": "www.pravda.com.ua",
        "ukr pravda": "www.pravda.com.ua",
        "ukrpravda": "www.pravda.com.ua",
    }
    def __init__(self):
        self._bot: Optional[Bot] = None
        self._app: Optional[Application] = None
        self._owner_id: int = int(settings.TELEGRAM_OWNER_CHAT_ID)
        self._notify_mode: str = getattr(settings, "NOTIFY_MODE", "minimal")

        # Очередь запросов на одобрение: request_id → asyncio.Future
        self._pending_approvals: dict[str, asyncio.Future] = {}
        # Anti-spam: remember last approval prompt per channel (e.g. publish_twitter)
        self._approval_last_sent_at: dict[str, str] = {}
        # Ожидаем уточнение по расписанию
        self._pending_schedule_update: dict | None = None
        # Ожидаем подтверждение системного действия (из свободного текста)
        self._pending_system_action: dict | None = None
        # Локальное подтверждение владельца для конкретного действия (приоритетнее общей очереди)
        self._pending_owner_confirmation: dict | None = None
        # Контекст выбора вариантов (когда бот прислал список "1., 2., 3.")
        self._pending_choice_context: dict | None = None
        # Ожидаем OTP-код для KDP auto-login
        self._pending_kdp_otp: dict | None = None
        # Serialize KDP browser-auth subprocesses to avoid Chromium resource races.
        self._kdp_auth_lock = asyncio.Lock()
        # Pending browser auth confirmations by service key (e.g. amazon_kdp, etsy).
        self._pending_service_auth: dict[str, dict] = {}
        # Last confirmed auth timestamps (runtime-memory).
        self._service_auth_confirmed: dict[str, str] = {}
        # Last discussed external service for contextual follow-ups.
        self._last_service_context: str = ""
        self._last_service_context_at: str = ""
        # Persistent auth/context state across restarts.
        self._auth_state_path = Path(
            str(getattr(settings, "TELEGRAM_AUTH_STATE_FILE", "runtime/service_auth_state.json") or "runtime/service_auth_state.json")
        )
        self._load_auth_state()
        self._telegram_conflict_mode: bool = False
        self._telegram_trace_path = Path(
            str(
                getattr(
                    settings,
                    "TELEGRAM_TRACE_FILE",
                    "runtime/telegram_trace.jsonl",
                )
                or "runtime/telegram_trace.jsonl"
            )
        )
        _install_reply_text_trace_patch(self._telegram_trace_path)

        # Обратные ссылки на модули — устанавливаются через set_modules()
        self._goal_engine = None
        self._llm_router = None
        self._decision_loop = None
        self._agent_registry = None
        self._self_healer = None
        self._self_updater = None
        self._conversation_engine = None
        self._judge_protocol = None
        self._finance = None
        self._skill_registry = None
        self._weekly_planner = None
        self._schedule_manager = None
        self._publisher_queue = None
        self._cancel_state = None
        self._owner_task_state = None

        # Маппинг текста кнопок → имена команд
        self._button_map: dict[str, str] = {
            "Главная": "start",
            "Статус": "status",
            "Задачи": "tasks",
            "Создать": "goal",
            "Входы": "auth_hub",
            "Отчёт": "report",
            "Еще": "more",
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

        logger.info("CommsAgent инициализирован", extra={"event": "init"})

    @staticmethod
    def _approval_channel(request_id: str) -> str:
        rid = str(request_id or "").strip().lower()
        if rid.startswith("publish_"):
            parts = rid.split("_")
            if len(parts) >= 2:
                return f"publish_{parts[1]}"
        return ""

    def _append_telegram_trace(self, direction: str, text: str, meta: dict[str, Any] | None = None) -> None:
        """Best-effort trace for Telegram E2E verification without extra pollers."""
        _append_telegram_trace_file(self._telegram_trace_path, direction, text, meta)

    def _resolve_button_command(self, text: str) -> str | None:
        """Resolve keyboard/menu button command with alias compatibility."""
        raw = str(text or "").strip()
        if not raw:
            return None
        if raw in self._button_map:
            return self._button_map[raw]
        normalized = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9_ ]+", " ", raw).strip().lower()
        normalized = re.sub(r"\s+", " ", normalized)
        aliases = {
            "статус": "status",
            "цели": "goals",
            "расходы": "spend",
            "новая цель": "goal",
            "задачи": "tasks",
            "создать": "goal",
            "входы": "auth_hub",
            "отчёт": "report",
            "отчет": "report",
            "еще": "more",
            "ещё": "more",
            "помощь": "help",
            "ежедневные": "help_daily",
            "редкие": "help_rare",
            "системные": "help_system",
            "главная": "start",
            "home": "start",
            "main": "start",
            "menu": "help",
            "daily": "help_daily",
            "daily commands": "help_daily",
            "rare": "help_rare",
            "system": "help_system",
            "system commands": "help_system",
        }
        return aliases.get(normalized)

    @staticmethod
    def _is_confirmed(args: list[str] | None) -> bool:
        if not args:
            return False
        token = str(args[0] or "").strip().lower()
        return token in {"yes", "y", "да", "confirm", "ok"}

    @staticmethod
    def _autonomy_max_enabled() -> bool:
        return bool(getattr(settings, "AUTONOMY_MAX_MODE", False))

    @staticmethod
    def _parse_bool_env(value: str) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_yes_token(text: str) -> bool:
        return str(text or "").strip().lower() in {"да", "yes", "ок", "ok", "approve", "✅", "👍"}

    @staticmethod
    def _is_no_token(text: str) -> bool:
        return str(text or "").strip().lower() in {"нет", "no", "reject", "отмена", "❌", "👎"}

    def _set_env_values(self, updates: dict[str, str]) -> bool:
        """Persist multiple env keys to .env and update runtime settings."""
        import os
        import re
        from pathlib import Path

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
                        setattr(settings, k, self._parse_bool_env(v))
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

    def _try_set_env_from_text(self, text: str) -> bool:
        """Parse KEY=VALUE messages and save to .env (owner only)."""
        import re

        # Accept formats: KEY=VALUE or "set KEY=VALUE"
        m = re.search(r"(?:^|\\bset\\s+)([A-Z0-9_]{3,})\\s*=\\s*([^\\s]+)", text, re.IGNORECASE)
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
        self._set_env_values({key: value})
        logger.info("Env key set via Telegram", extra={"event": "env_set", "context": {"key": key}})
        return True

    def _apply_llm_mode(self, mode: str) -> tuple[bool, str]:
        """Switch LLM routing profile quickly: free|prod."""
        m = str(mode or "").strip().lower()
        if m in {"free", "test", "gemini", "flash"}:
            self._set_env_values(
                {
                    "LLM_ROUTER_MODE": "free",
                    "LLM_FORCE_GEMINI_FREE": "true",
                    "LLM_FORCE_GEMINI_MODEL": "gemini-2.5-flash",
                    "LLM_ENABLED_MODELS": "gemini-2.5-flash",
                    "LLM_DISABLED_MODELS": "claude-haiku-4-5-20251001,gpt-4o-mini,claude-sonnet-4-6,o3,gpt-5,claude-opus-4-6,sonar-pro",
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
            self._set_env_values(
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
            free = bool(getattr(settings, "LLM_FORCE_GEMINI_FREE", False))
            enabled = str(getattr(settings, "LLM_ENABLED_MODELS", "") or "")
            disabled = str(getattr(settings, "LLM_DISABLED_MODELS", "") or "")
            model = str(getattr(settings, "LLM_FORCE_GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash")
            mode = str(getattr(settings, "LLM_ROUTER_MODE", "prod") or "prod")
            embed = bool(getattr(settings, "GEMINI_EMBEDDINGS_ENABLED", False))
            img = bool(getattr(settings, "GEMINI_ENABLE_IMAGEN", False))
            live = bool(getattr(settings, "GEMINI_LIVE_API_ENABLED", False))
            mode_name = "FREE (Gemini-only)" if free else "PROD (task-based)"
            return True, (
                f"LLM режим сейчас: {mode_name}\n"
                f"LLM_ROUTER_MODE={mode}\n"
                f"LLM_FORCE_GEMINI_MODEL={model}\n"
                f"GEMINI_EMBEDDINGS_ENABLED={str(embed).lower()} | GEMINI_ENABLE_IMAGEN={str(img).lower()} | GEMINI_LIVE_API_ENABLED={str(live).lower()}\n"
                f"LLM_ENABLED_MODELS={enabled or '(empty)'}\n"
                f"LLM_DISABLED_MODELS={disabled or '(empty)'}"
            )
        return False, "Использование: /llm_mode free | /llm_mode prod | /llm_mode status"

    @staticmethod
    def _is_kdp_login_request(text: str) -> bool:
        s = (text or "").strip().lower()
        if not s:
            return False
        has_target = any(x in s for x in ("amazon", "амазон", "kdp", "кдп"))
        has_action = any(x in s for x in ("зайди", "вход", "логин", "login", "auth", "авториза"))
        return has_target and has_action

    @staticmethod
    def _extract_otp_code(text: str) -> str:
        import re
        s = str(text or "").strip()
        m = re.search(r"\b(\d{6,8})\b", s)
        return m.group(1) if m else ""

    @staticmethod
    def _is_auth_done_text(text: str) -> bool:
        s = str(text or "").strip().lower()
        if not s:
            return False
        return any(
            token in s
            for token in ("я вошел", "я вошёл", "вошел", "вошёл", "готово", "ok", "ок", "done", "авторизовался", "авторизовалась")
        )

    @staticmethod
    def _detect_service_login_request(text: str) -> str:
        s = str(text or "").strip().lower()
        if not s:
            return ""
        has_action = any(
            x in s
            for x in (
                "зайди",
                "зайти",
                "войди",
                "вход",
                "логин",
                "login",
                "auth",
                "авториза",
                "войти",
                "открой",
                "обнови сес",
                "обновить сес",
                "refresh session",
                "перелогин",
                "перевойти",
            )
        )
        if not has_action:
            return ""
        for service, meta in CommsAgent._SERVICE_CATALOG.items():
            keys = tuple(meta.get("aliases") or ())
            if any(k in s for k in keys):
                return service
        custom = CommsAgent._extract_custom_login_target(s)
        if custom:
            return f"custom:{custom}"
        loose = CommsAgent._extract_loose_site_target(s)
        if loose:
            return f"custom:{loose}"
        return ""

    @staticmethod
    def _detect_service_from_text(text: str) -> str:
        s = str(text or "").strip().lower()
        if not s:
            return ""
        for service, meta in CommsAgent._SERVICE_CATALOG.items():
            keys = tuple(meta.get("aliases") or ())
            if any(k in s for k in keys):
                return service
        custom = CommsAgent._extract_custom_login_target(s)
        if custom:
            return f"custom:{custom}"
        loose = CommsAgent._extract_loose_site_target(s)
        if loose:
            return f"custom:{loose}"
        return ""

    @staticmethod
    def _service_auth_meta(service: str) -> tuple[str, str]:
        svc = str(service or "").strip().lower()
        if svc.startswith("custom:"):
            target = svc.split(":", 1)[1].strip()
            if target.startswith("http://") or target.startswith("https://"):
                auth_url = target
                host = urlparse(target).netloc or target
            else:
                host = target
                auth_url = f"https://{target}"
            return f"Сайт {host}", auth_url
        meta = CommsAgent._SERVICE_CATALOG.get(svc) or {}
        title = str(meta.get("title") or service)
        url = str(meta.get("url") or "")
        return title, url

    @staticmethod
    def _extract_custom_login_target(text: str) -> str:
        s = str(text or "").strip().lower()
        if not s:
            return ""
        m_url = re.search(r"(https?://[^\s<>\"]+)", s)
        if m_url:
            target = m_url.group(1).rstrip(").,;")
            try:
                parsed = urlparse(target)
                host = (parsed.netloc or "").strip().lower()
                if host:
                    return host
            except Exception:
                pass
        m_dom = re.search(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(?:/[^\s]*)?\b", s)
        if m_dom:
            domain = m_dom.group(1).strip()
            if domain in {"kdp.amazon.com", "x.com", "reddit.com", "etsy.com", "gumroad.com"}:
                return ""
            return domain
        return ""

    @staticmethod
    def _extract_loose_site_target(text: str) -> str:
        s = str(text or "").strip().lower()
        if not s:
            return ""
        compact = re.sub(r"\s+", " ", s)
        for alias, host in CommsAgent._SITE_ALIAS_URLS.items():
            if alias in compact:
                return host
        if "укрправд" in compact or "укр правд" in compact:
            return "www.pravda.com.ua"
        # Generic fallback: "зайди на <site>" even if owner omitted TLD.
        m = re.search(r"(?:зайди|зайти|открой|войти)\s+(?:на|в)?\s*([^\n\r,;!?]+)$", compact)
        if not m:
            return ""
        tail = m.group(1).strip().strip(".")
        if not tail:
            return ""
        if "amazon" in tail or "амазон" in tail or "kdp" in tail:
            return ""
        tail = tail.replace(" ", "")
        if not tail:
            return ""
        # If looks like host with dot - use as is.
        if re.match(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", tail):
            return tail
        # Last resort: append .com for short latin tokens.
        if re.match(r"^[a-z0-9-]{3,40}$", tail):
            return f"{tail}.com"
        return ""

    @staticmethod
    def _is_manual_auth_service(service: str) -> bool:
        svc = str(service or "").strip().lower()
        if svc.startswith("custom:"):
            return True
        meta = CommsAgent._SERVICE_CATALOG.get(svc) or {}
        return bool(meta.get("manual_fallback", False))

    @staticmethod
    def _requires_strict_auth_verification(service: str) -> bool:
        svc = str(service or "").strip().lower()
        # Сервисы, для которых запрещаем "ручное подтверждение" без реального live-check.
        return svc in {"amazon_kdp", "etsy", "gumroad", "printful", "twitter", "kofi"}

    def _touch_service_context(self, service: str) -> None:
        svc = str(service or "").strip().lower()
        if not svc:
            return
        self._last_service_context = svc
        self._last_service_context_at = datetime.now(timezone.utc).isoformat()
        self._save_auth_state()
        self._record_context_learning(
            skill_name="service_context_tracking",
            description=(
                "После команд входа запоминай последний сервис и используй его как контекст для коротких уточнений "
                "вроде 'статус', 'проверь аккаунт', 'вход ок?'."
            ),
            anti_pattern=(
                "Плохо: терять контекст и трактовать короткое 'статус' как общий статус VITO, "
                "когда владелец только что говорил о конкретной платформе."
            ),
            method={"service": svc},
        )

    def _has_fresh_service_context(self, max_age_minutes: int = 180) -> bool:
        if not self._last_service_context:
            return False
        stamp = str(self._last_service_context_at or "").strip()
        if not stamp:
            return True
        try:
            dt = datetime.fromisoformat(stamp)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_sec = (datetime.now(timezone.utc) - dt).total_seconds()
            return age_sec <= max(60, int(max_age_minutes) * 60)
        except Exception:
            return True

    def _get_memory_manager(self):
        # Prefer shared runtime memory from conversation/decision loop.
        candidates = [getattr(self, "_conversation_engine", None), getattr(self, "_decision_loop", None)]
        for obj in candidates:
            mm = getattr(obj, "memory", None) if obj else None
            if mm and hasattr(mm, "save_skill") and hasattr(mm, "save_pattern"):
                return mm
        return None

    def _record_context_learning(self, skill_name: str, description: str, anti_pattern: str, method: dict | None = None) -> None:
        mm = self._get_memory_manager()
        if mm is None:
            return
        try:
            mm.save_skill(
                name=skill_name,
                description=description,
                agent="comms_agent",
                task_type="nlu_context",
                method=method or {},
            )
            mm.save_pattern(
                category="owner_context",
                key=skill_name,
                value=description,
                confidence=0.95,
            )
            mm.save_pattern(
                category="anti_pattern",
                key=f"{skill_name}_anti",
                value=anti_pattern,
                confidence=0.95,
            )
        except Exception:
            pass

    def _load_auth_state(self) -> None:
        path = self._auth_state_path
        try:
            if not path.exists():
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
            confirmed = payload.get("service_auth_confirmed", {})
            if isinstance(confirmed, dict):
                self._service_auth_confirmed = {
                    str(k).strip().lower(): str(v)
                    for k, v in confirmed.items()
                    if str(k).strip()
                }
            self._last_service_context = str(payload.get("last_service_context", "") or "").strip().lower()
            self._last_service_context_at = str(payload.get("last_service_context_at", "") or "").strip()
        except Exception:
            pass

    def _save_auth_state(self) -> None:
        path = self._auth_state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "service_auth_confirmed": self._service_auth_confirmed,
                "last_service_context": self._last_service_context,
                "last_service_context_at": self._last_service_context_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _mark_service_auth_confirmed(self, service: str) -> None:
        svc = str(service or "").strip().lower()
        if not svc:
            return
        self._service_auth_confirmed[svc] = datetime.now(timezone.utc).isoformat()
        self._save_auth_state()

    def _clear_service_auth_confirmed(self, service: str) -> None:
        svc = str(service or "").strip().lower()
        if not svc:
            return
        if svc in self._service_auth_confirmed:
            self._service_auth_confirmed.pop(svc, None)
            self._save_auth_state()

    @staticmethod
    def _is_challenge_detail(detail: str) -> bool:
        s = str(detail or "").strip().lower()
        return any(x in s for x in ("challenge", "captcha", "datadome", "2fa", "otp_required"))

    @staticmethod
    def _manual_capture_hint(service: str) -> str:
        svc = str(service or "").strip().lower()
        if svc == "etsy":
            return (
                "Требуется обновление серверной сессии Etsy: "
                "`python3 scripts/etsy_auth_helper.py browser-capture --storage-path runtime/etsy_storage_state.json`"
            )
        return "Нужен ручной вход в серверной browser-сессии и сохранение storage_state."

    @staticmethod
    def _service_needs_session_refresh_text(service: str, title: str, detail: str) -> str:
        base = f"{title}: нужно обновить серверную сессию."
        d = str(detail or "").strip()
        if d:
            return f"{base}\nДеталь: {d}"
        return base

    @staticmethod
    def _is_status_prompt(text: str) -> bool:
        s = str(text or "").strip().lower()
        return any(
            token in s
            for token in (
                "статус",
                "status",
                "состояние аккаунта",
                "состояние",
                "state",
                "проверь аккаунт",
                "покажи аккаунт",
                "проверка входа",
                "авториз",
                "логин",
            )
        )

    @staticmethod
    def _is_inventory_prompt(text: str) -> bool:
        s = str(text or "").strip().lower()
        if not s:
            return False
        # Creation/publish intents must not be misrouted as inventory checks
        # just because they contain words like "листинг"/"товар".
        if any(
            x in s
            for x in (
                "создай",
                "создать",
                "опубликуй",
                "опубликовать",
                "размести",
                "разместить",
                "заполни",
                "заполнить",
                "сгенерируй",
                "сделай",
                "make",
                "create",
                "publish",
                "post ",
            )
        ):
            return False
        if any(x in s for x in ("тренд", "trend", "ниш", "niche", "конкурент", "рынок")):
            return False
        if any(x in s for x in ("профиль", "profile")) and any(x in s for x in ("настрой", "settings")):
            return False
        return any(
            token in s
            for token in (
                "аккаунт",
                "account",
                "кабинет",
                "профиль",
                "товар",
                "товары",
                "продукт",
                "продукты",
                "листинг",
                "листинги",
                "каталог",
                "ассортимент",
                "products",
                "listings",
                "inventory",
            )
        )

    def _detect_contextual_service_status_request(self, text: str) -> str:
        s = str(text or "").strip().lower()
        if not s or not self._is_status_prompt(s):
            return ""
        explicit = self._detect_service_from_text(s)
        if explicit:
            return explicit
        if any(x in s for x in ("vito", "вито", "система", "system")):
            return ""
        if self._has_fresh_service_context():
            return self._last_service_context
        if self._pending_service_auth:
            try:
                return next(reversed(self._pending_service_auth))
            except Exception:
                return ""
        return ""

    def _detect_contextual_service_inventory_request(self, text: str) -> str:
        s = str(text or "").strip().lower()
        if not s or not self._is_inventory_prompt(s):
            return ""
        explicit = self._detect_service_from_text(s)
        if explicit:
            return explicit
        if any(x in s for x in ("vito", "вито", "система", "system")):
            return ""
        if self._has_fresh_service_context():
            return self._last_service_context
        if self._pending_service_auth:
            try:
                return next(reversed(self._pending_service_auth))
            except Exception:
                return ""
        return ""

    @staticmethod
    def _is_auth_issue_prompt(text: str) -> bool:
        s = str(text or "").strip().lower()
        if not s:
            return False
        return any(
            token in s
            for token in (
                "почему не заходит",
                "не заходит",
                "не входит",
                "не могу войти",
                "не получается войти",
                "why can",
                "why not login",
                "login issue",
            )
        )

    def _format_service_auth_status(self, service: str) -> str:
        svc = str(service or "").strip().lower()
        if not svc:
            return "Не понял, по какому сервису показать статус."
        title, auth_url = self._service_auth_meta(svc)
        if svc in self._pending_service_auth:
            return (
                f"{title}: ожидается подтверждение входа.\n"
                f"Ссылка: {auth_url}\n"
                "После входа нажми «Я вошел» или напиши «готово»."
            )
        if self._service_auth_confirmed.get(svc):
            return f"{title}: вход подтверждён. Повторный логин сейчас не требуется."
        return f"{title}: вход пока не подтверждён. Напиши «зайди на {title}» для авторизации."

    async def _format_service_auth_status_live(self, service: str) -> str:
        svc = str(service or "").strip().lower()
        base = self._format_service_auth_status(svc)
        if not svc:
            return base
        title, _ = self._service_auth_meta(svc)
        if svc in self._pending_service_auth:
            return base

        # Для Amazon делаем только probe (без авто-логина), чтобы статус не триггерил новый вход.
        if svc == "amazon_kdp":
            try:
                probe_rc, _ = await self._run_kdp_probe_stable()
                if probe_rc == 0:
                    self._mark_service_auth_confirmed(svc)
                    return f"{title}: подключение активно (live-check OK). Повторный логин не требуется."
                if self._service_auth_confirmed.get(svc):
                    return (
                        f"{title}: вход ранее подтверждён, но live-check сейчас не прошёл. "
                        "Если действия в Amazon не выполняются, запусти вход заново."
                    )
                return (
                    f"{title}: live-check не подтвердил сессию. "
                    f"Нужна авторизация: зайди на {title}."
                )
            except Exception:
                return (
                    f"{title}: статус по кэшу — вход ранее подтверждён, "
                    "но live-check сейчас недоступен."
                    if self._service_auth_confirmed.get(svc)
                    else f"{title}: вход пока не подтверждён."
                )

        if self._requires_strict_auth_verification(svc):
            try:
                ok, detail = await self._verify_service_auth(svc)
                if ok:
                    self._mark_service_auth_confirmed(svc)
                    return f"{title}: подключение активно (live-check OK). Повторный логин не требуется."
                has_storage, _ = self._has_cookie_storage_state(svc)
                if has_storage and self._service_auth_confirmed.get(svc):
                    return (
                        f"{title}: есть сохранённая browser-сессия, но прямой live-check сейчас не прошёл. "
                        "Если действие не выполняется, запусти вход заново."
                    )
                self._clear_service_auth_confirmed(svc)
                return f"{title}: вход не подтверждён (live-check fail). {detail}"
            except Exception as e:
                self._clear_service_auth_confirmed(svc)
                return f"{title}: вход не подтверждён. Ошибка проверки: {e}"

        # Для остальных сервисов сохраняем быстрый статус без тяжёлого live probe.
        return base

    async def _format_service_inventory_snapshot(self, service: str) -> str:
        svc = str(service or "").strip().lower()
        if not svc:
            return "Не понял, по какому сервису проверить товары."
        title, _ = self._service_auth_meta(svc)

        if svc == "amazon_kdp":
            try:
                probe_rc, _ = await self._run_kdp_probe_stable()
                if probe_rc != 0:
                    return (
                        f"{title}: не вижу активной сессии аккаунта (live-check не пройден). "
                        "Сначала зайди в аккаунт, потом повтори проверку товаров."
                    )
            except Exception:
                pass
            try:
                inv_rc, inv_out = await self._run_kdp_inventory_probe()
                if inv_rc == 0:
                    payload_line = ""
                    for ln in reversed((inv_out or "").splitlines()):
                        ln = ln.strip()
                        if ln.startswith("{") and ln.endswith("}"):
                            payload_line = ln
                            break
                    if payload_line:
                        data = json.loads(payload_line)
                        if bool(data.get("ok", False)):
                            items = data.get("items") or []
                            if isinstance(items, list):
                                noise = (
                                    "how would you rate your experience",
                                    "visit our help center",
                                    "thank you for your feedback",
                                )
                                cleaned: list[str] = []
                                seen: set[str] = set()
                                for it in items:
                                    t = str(it or "").strip()
                                    if not t:
                                        continue
                                    low = t.lower()
                                    if any(n in low for n in noise):
                                        continue
                                    if low in seen:
                                        continue
                                    seen.add(low)
                                    cleaned.append(t)
                                items = cleaned
                            count = int(data.get("products_count", 0) or 0)
                            if isinstance(items, list):
                                count = len(items)
                            lines = [f"{title}: состояние аккаунта", f"- Товаров/книг: {count}"]
                            if items:
                                lines.append("- Примеры:")
                                for it in items[:5]:
                                    lines.append(f"  - {str(it)[:120]}")
                            return "\n".join(lines)
            except Exception:
                pass

        if not self._agent_registry:
            return f"{title}: модуль проверки товаров не подключён."
        try:
            result = await self._agent_registry.dispatch("sales_check", platform=svc)
        except Exception as e:
            return f"{title}: ошибка запроса данных аккаунта: {e}"

        if not result or not getattr(result, "success", False):
            return f"{title}: не удалось получить данные аккаунта."
        payload = getattr(result, "output", {}) or {}
        data = payload.get(svc, payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            return f"{title}: данные аккаунта получены в неподдерживаемом формате."
        if data.get("error"):
            return f"{title}: проверка аккаунта вернула ошибку: {data.get('error')}"

        lines = [f"{title}: состояние аккаунта"]
        has_metrics = False

        for key, label in (
            ("products_count", "Товаров"),
            ("listings", "Листингов"),
            ("sales", "Продаж"),
            ("orders", "Заказов"),
            ("total_views", "Просмотров"),
            ("total_favorites", "Добавили в избранное"),
        ):
            if key in data:
                lines.append(f"- {label}: {data.get(key)}")
                has_metrics = True
        if "revenue" in data:
            try:
                lines.append(f"- Выручка: ${float(data.get('revenue') or 0.0):.2f}")
            except Exception:
                lines.append(f"- Выручка: {data.get('revenue')}")
            has_metrics = True

        if not has_metrics:
            if data.get("raw_data"):
                lines.append("- Детальные данные получены, но формат неструктурирован.")
            else:
                lines.append("- Метрики товаров не вернулись. Возможно, у аккаунта нет доступных данных через текущий канал.")

        return "\n".join(lines)

    async def _run_kdp_probe(self) -> tuple[int, str]:
        storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
        base = [
            "python3",
            "scripts/kdp_auth_helper.py",
            "probe",
            "--storage-path",
            storage,
            "--headless",
        ]
        variants = [
            base,
            ["xvfb-run", "-a", *base],
        ]
        return await self._run_kdp_variants(variants, timeout_sec=120)

    async def _run_kdp_probe_stable(self) -> tuple[int, str]:
        rc, out = await self._run_kdp_probe()
        if rc == 0:
            return rc, out
        await asyncio.sleep(0.8)
        return await self._run_kdp_probe()

    async def _run_kdp_inventory_probe(self) -> tuple[int, str]:
        storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
        base = [
            "python3",
            "scripts/kdp_auth_helper.py",
            "inventory",
            "--storage-path",
            storage,
            "--headless",
        ]
        variants = [
            base,
            ["xvfb-run", "-a", *base],
        ]
        return await self._run_kdp_variants(variants, timeout_sec=150)

    async def _run_kdp_variants(self, variants: list[list[str]], timeout_sec: int) -> tuple[int, str]:
        """Run KDP helper command variants, returning first success or full diagnostics."""
        async with self._kdp_auth_lock:
            chunks: list[str] = []
            last_rc = 1
            for cmd in variants:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
                output = (out_b or b"").decode("utf-8", errors="ignore")
                rc = int(proc.returncode or 0)
                last_rc = rc
                cmd_txt = " ".join(cmd)
                chunks.append(f"$ {cmd_txt}\n{output}")
                if rc == 0:
                    return 0, "\n\n--- variant ---\n".join(chunks)
            return last_rc, "\n\n--- variant ---\n".join(chunks)

    async def _run_etsy_auto_login(self) -> tuple[int, str]:
        storage = str(getattr(settings, "ETSY_STORAGE_STATE_FILE", "runtime/etsy_storage_state.json") or "runtime/etsy_storage_state.json")
        cmd = [
            "python3",
            "scripts/etsy_auth_helper.py",
            "auto-login",
            "--timeout-sec",
            "120",
            "--storage-path",
            storage,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        output = (out_b or b"").decode("utf-8", errors="ignore")
        return int(proc.returncode or 0), output

    async def _run_etsy_remote_session(self, action: str = "status") -> tuple[int, str]:
        cmd = [
            "bash",
            "scripts/etsy_remote_session.sh",
            str(action or "status"),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
        output = (out_b or b"").decode("utf-8", errors="ignore")
        return int(proc.returncode or 0), output

    async def _run_remote_auth_session(self, service: str, action: str = "status") -> tuple[int, str]:
        cmd = [
            "bash",
            "scripts/remote_auth_session.sh",
            str(service or "").strip().lower(),
            str(action or "status"),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = (out_b or b"").decode("utf-8", errors="ignore")
        return int(proc.returncode or 0), output

    @staticmethod
    def _parse_remote_kv(text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in str(text or "").splitlines():
            s = line.strip()
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            out[k.strip().lower()] = v.strip()
        return out

    def _service_storage_state_path(self, service: str) -> Path | None:
        svc = str(service or "").strip().lower()
        raw = ""
        if svc == "amazon_kdp":
            raw = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
        elif svc == "etsy":
            raw = str(getattr(settings, "ETSY_STORAGE_STATE_FILE", "runtime/etsy_storage_state.json") or "runtime/etsy_storage_state.json")
        elif svc == "kofi":
            raw = str(getattr(settings, "KOFI_STORAGE_STATE_FILE", "runtime/kofi_storage_state.json") or "runtime/kofi_storage_state.json")
        elif svc == "printful":
            raw = str(getattr(settings, "PRINTFUL_STORAGE_STATE_FILE", "runtime/printful_storage_state.json") or "runtime/printful_storage_state.json")
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    def _has_cookie_storage_state(self, service: str, since_iso: str = "") -> tuple[bool, str]:
        p = self._service_storage_state_path(service)
        if p is None:
            return False, "no_storage_path"
        if not p.exists():
            return False, "storage_missing"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            cookies = data.get("cookies") if isinstance(data, dict) else None
            if not isinstance(cookies, list) or not cookies:
                return False, "cookies_missing"
            if since_iso:
                try:
                    req_dt = datetime.fromisoformat(str(since_iso))
                    if req_dt.tzinfo is None:
                        req_dt = req_dt.replace(tzinfo=timezone.utc)
                    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                    if mtime < req_dt:
                        return False, "storage_not_updated_after_login"
                except Exception:
                    pass
            return True, "storage_cookies_ok"
        except Exception:
            return False, "storage_parse_failed"

    async def _verify_service_auth(self, service: str) -> tuple[bool, str]:
        svc = str(service or "").strip().lower()
        if not svc:
            return False, "service_missing"
        if svc == "amazon_kdp":
            probe_rc, probe_out = await self._run_kdp_probe_stable()
            if probe_rc == 0:
                return True, "Amazon KDP сессия подтверждена."
            has_storage, _ = self._has_cookie_storage_state("amazon_kdp")
            if has_storage:
                return True, "Amazon KDP: browser storage_state зафиксирован."
            rc, out = await self._run_kdp_auto_login()
            if rc == 0:
                return True, "Amazon KDP вход подтверждён и сессия сохранена."
            if "OTP_REQUIRED" in out:
                self._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat()}
                return False, "Для Amazon нужен код из аутентификатора. Отправь 6 цифр."
            return False, "Не удалось подтвердить вход Amazon автоматически."
        if svc == "printful":
            try:
                from platforms.printful import PrintfulPlatform

                p = PrintfulPlatform()
                ok = await p.authenticate()
                await p.close()
                if ok:
                    return True, "Printful авторизация подтверждена."
                has_storage, _ = self._has_cookie_storage_state("printful")
                if has_storage:
                    return True, "Printful: browser storage_state зафиксирован."
                return False, "Printful авторизация не подтверждена."
            except Exception:
                return False, "Ошибка проверки Printful."
        if svc == "gumroad":
            try:
                from platforms.gumroad import GumroadPlatform

                p = GumroadPlatform()
                ok = await p.authenticate()
                await p.close()
                return ok, ("Gumroad авторизация подтверждена." if ok else "Gumroad авторизация не подтверждена.")
            except Exception:
                return False, "Ошибка проверки Gumroad."
        if svc == "twitter":
            try:
                from platforms.twitter import TwitterPlatform

                p = TwitterPlatform()
                ok = await p.authenticate()
                await p.close()
                if ok:
                    return True, "Twitter/X авторизация подтверждена."
                return False, "Twitter/X API пока не подтверждает вход. Зафиксировал ручную авторизацию."
            except Exception:
                return False, "Twitter/X API проверка недоступна. Зафиксировал ручную авторизацию."
        if svc == "etsy":
            try:
                from platforms.etsy import EtsyPlatform

                p = EtsyPlatform()
                ok = await p.authenticate()
                await p.close()
                if ok:
                    return True, "Etsy авторизация подтверждена."
                mode = str(getattr(settings, "ETSY_MODE", "api") or "api").lower()
                if mode in {"browser", "browser_only"}:
                    has_storage, _ = self._has_cookie_storage_state("etsy")
                    if has_storage:
                        return True, "Etsy: browser storage_state зафиксирован."
                    rc, out = await self._run_etsy_auto_login()
                    if rc == 0:
                        return True, "Etsy browser-сессия захвачена автоматически."
                    low = str(out or "").lower()
                    if "otp_required" in low or "challenge" in low or "captcha" in low or "datadome" in low:
                        return False, "Etsy challenge/captcha: нужен ручной server-capture сессии."
                    return False, "Etsy browser-сессия не подтверждена. Авто-вход не прошёл."
                return False, "Etsy API не подтвердил вход. Зафиксировал ручную авторизацию."
            except Exception:
                mode = str(getattr(settings, "ETSY_MODE", "api") or "api").lower()
                if mode in {"browser", "browser_only"}:
                    return False, "Etsy browser-проверка недоступна."
                return False, "Etsy API проверка недоступна. Зафиксировал ручную авторизацию."
        if svc == "kofi":
            try:
                from platforms.kofi import KofiPlatform

                p = KofiPlatform()
                ok = await p.authenticate()
                await p.close()
                if ok:
                    return True, "Ko-fi авторизация подтверждена."
                has_storage, _ = self._has_cookie_storage_state("kofi")
                if has_storage:
                    return True, "Ko-fi: browser storage_state зафиксирован."
                return False, "Ko-fi авторизация не подтверждена."
            except Exception:
                return False, "Ko-fi проверка недоступна."
        if svc == "reddit":
            return False, "Reddit в browser_only режиме; зафиксировал ручную авторизацию."
        if self._is_manual_auth_service(svc):
            title, _ = self._service_auth_meta(svc)
            return False, f"{title}: подтверждение только вручную (browser-only)."
        return False, "Проверка сервиса не реализована."

    async def _start_service_auth_flow(self, service: str, send_reply, with_button: bool = True) -> bool:
        svc = str(service or "").strip().lower()
        if not svc:
            return False
        self._touch_service_context(svc)
        title, auth_url = self._service_auth_meta(svc)
        if not auth_url:
            return False
        if self._requires_strict_auth_verification(svc):
            ok = False
            try:
                # Amazon must be validated by real live-check probe only.
                # Cookie/storage presence alone is not enough to claim active session.
                if svc == "amazon_kdp":
                    probe_rc, _ = await self._run_kdp_probe_stable()
                    ok = probe_rc == 0
                else:
                    ok, _ = await self._verify_service_auth(svc)
            except Exception:
                ok = False
            if ok:
                self._mark_service_auth_confirmed(svc)
                await send_reply(f"{title}: активная сессия уже подтверждена, повторный логин не требуется.")
                return True
            self._clear_service_auth_confirmed(svc)
            # Для strict-сервисов не доверяем age-based кэшу вовсе.
            # Всегда продолжаем в полноценный auth flow.

        # Browser-capture remote flow for key platforms with server-side session files.
        if svc in {"etsy", "amazon_kdp", "kofi", "printful"}:
            rc, out = await self._run_remote_auth_session(svc, "start")
            if rc == 0:
                kv = self._parse_remote_kv(out)
                remote_url = kv.get("remote_url", "")
                direct_url = kv.get("direct_url", "")
                vnc_password = kv.get("vnc_password", "")
                self._pending_service_auth[svc] = {
                    "service": svc,
                    "url": remote_url or direct_url or auth_url,
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                    "mode": "remote",
                }
                msg = (
                    f"Запускаю вход {title} в удалённом браузере сервера.\n"
                    f"Ссылка: {remote_url or direct_url or auth_url}\n"
                    f"Пароль: {vnc_password or f'(см. /auth {svc} remote)'}\n"
                    "После входа нажми «Я вошел»."
                )
                if direct_url:
                    msg += f"\nРезервная ссылка: {direct_url}"
                if with_button and (remote_url or direct_url or auth_url):
                    kb = InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton(f"Открыть вход {title}", url=(remote_url or direct_url or auth_url))],
                            [InlineKeyboardButton("Я вошел", callback_data=f"auth_done:{svc}")],
                            [InlineKeyboardButton("Отмена", callback_data=f"auth_cancel:{svc}")],
                        ]
                    )
                    await send_reply(msg, kb)
                else:
                    await send_reply(msg)
                return True

        last = self._service_auth_confirmed.get(svc, "")
        if last and not self._requires_strict_auth_verification(svc):
            try:
                dt = datetime.fromisoformat(last)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_sec = (datetime.now(timezone.utc) - dt).total_seconds()
                if age_sec < 12 * 3600:
                    await send_reply(f"{title}: вход уже подтверждён недавно. Можешь работать без повторного логина.")
                    return True
            except Exception:
                pass
        payload = {
            "service": svc,
            "url": auth_url,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        self._pending_service_auth[svc] = payload
        if with_button:
            kb = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(f"Войти в {title}", url=auth_url)],
                    [InlineKeyboardButton("Я вошел", callback_data=f"auth_done:{svc}")],
                    [InlineKeyboardButton("Отмена", callback_data=f"auth_cancel:{svc}")],
                ]
            )
            await send_reply(
                f"Открой вход в {title}, авторизуйся, затем нажми «Я вошел».",
                kb,
            )
            return True
        await send_reply(
            f"Ссылка для входа в {title}: {auth_url}\nПосле входа ответь: «я вошел»."
        )
        return True

    async def _run_kdp_auto_login(self, otp_code: str = "") -> tuple[int, str]:
        storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
        base = [
            "python3",
            "scripts/kdp_auth_helper.py",
            "auto-login",
            "--timeout-sec",
            "180",
            "--storage-path",
            storage,
        ]
        if otp_code:
            base.extend(["--otp-code", otp_code])
        variants = [
            base,
            ["xvfb-run", "-a", *base],
        ]
        return await self._run_kdp_variants(variants, timeout_sec=220)

    async def _run_kdp_prepare_otp(self) -> tuple[int, str]:
        base = [
            "python3",
            "scripts/kdp_auth_helper.py",
            "prepare-otp",
            "--timeout-sec",
            "120",
            "--preauth-state-path",
            "runtime/kdp_preauth_state.json",
            "--preauth-meta-path",
            "runtime/kdp_preauth_meta.json",
        ]
        variants = [
            base,
            ["xvfb-run", "-a", *base],
        ]
        return await self._run_kdp_variants(variants, timeout_sec=180)

    async def _cleanup_browser_runtime(self) -> None:
        """Keep browser runtime untouched to avoid killing active startup flow."""
        return

    async def _run_kdp_submit_otp(self, otp_code: str) -> tuple[int, str]:
        storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
        base = [
            "python3",
            "scripts/kdp_auth_helper.py",
            "submit-otp",
            "--timeout-sec",
            "120",
            "--preauth-state-path",
            "runtime/kdp_preauth_state.json",
            "--preauth-meta-path",
            "runtime/kdp_preauth_meta.json",
            "--storage-path",
            storage,
            "--otp-code",
            str(otp_code or "").strip(),
        ]
        variants = [
            base,
            ["xvfb-run", "-a", *base],
        ]
        return await self._run_kdp_variants(variants, timeout_sec=180)

    @staticmethod
    def _kdp_prepare_has_mfa_evidence(output: str) -> bool:
        low = str(output or "").lower()
        return ("otp_ready" in low) or ("/ap/mfa" in low) or ("mfa.arb" in low)

    def _kdp_preauth_ready(self) -> bool:
        st = PROJECT_ROOT / "runtime" / "kdp_preauth_state.json"
        meta = PROJECT_ROOT / "runtime" / "kdp_preauth_meta.json"
        if not st.exists():
            return False
        if not meta.exists():
            return True
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            url = str(data.get("url") or "").lower()
            return ("/ap/mfa" in url) or ("mfa.arb" in url) or bool(data.get("prepared", False))
        except Exception:
            return True

    def _reset_kdp_auth_state_files(self) -> None:
        """Force fresh KDP auth by clearing preauth+storage artifacts."""
        paths = [
            PROJECT_ROOT / "runtime" / "kdp_preauth_state.json",
            PROJECT_ROOT / "runtime" / "kdp_preauth_meta.json",
            PROJECT_ROOT / "runtime" / "kdp_storage_state.json",
        ]
        for p in paths:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    async def _handle_kdp_login_flow(self, text: str, send_reply, with_button: bool = False) -> bool:
        maybe_otp = self._extract_otp_code(text)
        if self._pending_kdp_otp and maybe_otp:
            await send_reply("Код получен. Подтверждаю вход в Amazon KDP...")
            await self._cleanup_browser_runtime()
            # If session already became valid, accept immediately.
            try:
                pre_probe_rc, _ = await self._run_kdp_probe_stable()
            except Exception:
                pre_probe_rc = 1
            if pre_probe_rc == 0:
                self._pending_kdp_otp = None
                self._mark_service_auth_confirmed("amazon_kdp")
                self._pending_service_auth.pop("amazon_kdp", None)
                await send_reply("Готово: вход в KDP подтвержден (live-check OK).")
                return True
            prepared_mode = bool((self._pending_kdp_otp or {}).get("prepared", False)) or self._kdp_preauth_ready()
            # Stable Telegram path:
            # if OTP page is already prepared, submit code into this prepared session first.
            # Rebuilding the full login flow before OTP increases code expiry risk.
            attempts: list[tuple[str, tuple[int, str]]] = []
            if prepared_mode:
                attempts.append(("submit_otp_prepared", await self._run_kdp_submit_otp(maybe_otp)))
                if attempts[-1][1][0] != 0:
                    # Prepared session may go stale; refresh it and retry submit once.
                    prep_rc, _prep_out = await self._run_kdp_prepare_otp()
                    if prep_rc == 0 or self._kdp_prepare_has_mfa_evidence(_prep_out):
                        attempts.append(("submit_otp_refreshed", await self._run_kdp_submit_otp(maybe_otp)))
            if not attempts:
                # No prepared MFA session: fall back to direct full login with OTP.
                attempts.append(("auto_login", await self._run_kdp_auto_login(otp_code=maybe_otp)))

            for _mode, (rc_try, _out_try) in attempts:
                if rc_try == 0:
                    self._pending_kdp_otp = None
                    self._mark_service_auth_confirmed("amazon_kdp")
                    self._pending_service_auth.pop("amazon_kdp", None)
                    await send_reply("Готово: вход в KDP подтвержден, сессия сохранена.")
                    return True
                try:
                    probe_rc_try, _ = await self._run_kdp_probe_stable()
                except Exception:
                    probe_rc_try = 1
                if probe_rc_try == 0:
                    self._pending_kdp_otp = None
                    self._mark_service_auth_confirmed("amazon_kdp")
                    self._pending_service_auth.pop("amazon_kdp", None)
                    await send_reply("Готово: вход в KDP подтвержден (live-check OK).")
                    return True

            out = attempts[0][1][1] if attempts else ""
            out2 = attempts[-1][1][1] if attempts else ""
            # Keep pending OTP mode to let owner send a fresh code immediately.
            self._pending_kdp_otp = {
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "retry": True,
                "prepared": prepared_mode,
            }
            msg = "Код не подтвердился. Пришли новый 6-значный код (без /kdp_login)."
            low_all = f"{str(out or '').lower()}\n{str(out2 or '').lower()}"
            if "otp_rejected" in low_all or "expired" in low_all or "invalid" in low_all:
                msg = "Код неверный или истёк. Пришли новый 6-значный код сразу после генерации."
            elif "chromium launch failed" in low_all or "error: auto_login_exception" in low_all:
                msg = "Не смог запустить браузерную сессию Amazon. Повтори «зайди на амазон» через 10 секунд."
            await send_reply(msg)
            logger.warning(
                "KDP OTP login failed",
                extra={
                    "event": "kdp_login_otp_failed",
                    "context": {
                        "output_head": (out[:4000] if isinstance(out, str) else str(out)),
                        "output_tail": (out[-4000:] if isinstance(out, str) else str(out)),
                        "retry_output_head": (out2[:4000] if isinstance(out2, str) else str(out2)),
                        "retry_output_tail": (out2[-4000:] if isinstance(out2, str) else str(out2)),
                    },
                },
            )
            return True

        if not self._is_kdp_login_request(text):
            return False

        force_fresh = bool(getattr(settings, "KDP_AUTH_FORCE_FRESH_EACH_LOGIN", False))
        if not force_fresh:
            # Sticky session mode: if KDP session is alive, do not relogin.
            try:
                probe_rc, _ = await self._run_kdp_probe_stable()
            except Exception:
                probe_rc = 1
            if probe_rc == 0:
                self._mark_service_auth_confirmed("amazon_kdp")
                await send_reply("Amazon KDP: активная сессия уже подтверждена, повторный логин не требуется.")
                return True
        else:
            # Force fresh auth each time owner explicitly requests Amazon login.
            self._pending_kdp_otp = None
            self._pending_service_auth.pop("amazon_kdp", None)
            self._clear_service_auth_confirmed("amazon_kdp")
            self._reset_kdp_auth_state_files()

        # 2) Предпочтительный путь: подготовить MFA страницу и просить OTP только после этого.
        rc, out = 1, ""
        attempt_outputs: list[str] = []

        def _is_mfa_required(_rc: int, _low: str) -> bool:
            mfa_hints = ("otp_required", "otp code not provided", "/ap/mfa", "mfa?", "otp_ready")
            return _rc in {2, 3} or any(h in _low for h in mfa_hints)

        for attempt in range(5):
            await self._cleanup_browser_runtime()
            rc, out = await self._run_kdp_prepare_otp()
            low = str(out or "").lower()
            attempt_outputs.append(str(out or ""))
            if rc == 0:
                if "otp_ready" in low:
                    self._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat(), "prepared": True}
                    await send_reply("Нужен 6-значный код из Amazon/Authenticator. Отправь его одним сообщением.")
                    return True
                # prepare-otp may also report already logged in
                self._pending_kdp_otp = None
                self._mark_service_auth_confirmed("amazon_kdp")
                self._pending_service_auth.pop("amazon_kdp", None)
                await send_reply("Готово: вход в Amazon KDP подтверждён и сессия сохранена.")
                return True
            if _is_mfa_required(rc, low):
                self._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat(), "prepared": True}
                await send_reply("Нужен 6-значный код из Amazon/Authenticator. Отправь его одним сообщением.")
                return True
            if attempt < 4:
                await asyncio.sleep(1.0 + attempt)

        # Some Playwright runs fail after reaching MFA URL; treat clear MFA URL evidence as prepared state.
        all_low = "\n".join(attempt_outputs).lower()
        if "/ap/mfa" in all_low or "mfa.arb" in all_low:
            self._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat(), "prepared": True}
            await send_reply("Нужен 6-значный код из Amazon/Authenticator. Отправь его одним сообщением.")
            return True

        # 3) Без VNC fallback для Amazon в обычном диалоге:
        # remote-browser часто нестабилен на сервере и даёт "черный экран".
        # Возвращаем явный next-step вместо запуска VNC-сессии.
        summary = ""
        try:
            lines = [ln.strip() for ln in str(out or "").splitlines() if ln.strip()]
            reason = ""
            for ln in reversed(lines):
                if ln.lower().startswith("error:"):
                    reason = ln
                    break
            if not reason and lines:
                reason = lines[-1]
            if reason and reason.strip().lower() not in {"url=", "reason: url=", "причина: url="} and "[pid=" not in reason.lower():
                summary = f" Причина: {reason[:180]}"
        except Exception:
            summary = ""
        # Fallback: keep OTP flow active anyway and accept code in chat.
        # In practice direct auto-login with provided OTP can still succeed
        # even when prepare-otp stage is flaky.
        prepared_guess = self._kdp_prepare_has_mfa_evidence(out) or self._kdp_preauth_ready()
        self._pending_kdp_otp = {
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "forced": True,
            "prepared": bool(prepared_guess),
        }
        await send_reply(
            "Не смог стабильно открыть окно ввода кода Amazon. "
            "Пришли 6-значный код из Amazon/Authenticator — попробую прямой вход."
            f"{summary}"
        )
        logger.warning(
            "KDP auto-login failed without OTP; remote fallback suppressed",
            extra={
                "event": "kdp_login_auto_failed_no_remote",
                "context": {
                    "output_head": (out[:4000] if isinstance(out, str) else str(out)),
                    "output_tail": (out[-4000:] if isinstance(out, str) else str(out)),
                },
            },
        )
        return True

    def _log_owner_request(self, text: str, source: str = "text") -> None:
        """Append owner requests to requirements log with timestamp."""
        try:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).isoformat()
            log_path = PROJECT_ROOT / "docs" / "OWNER_REQUIREMENTS_LOG.md"
            entry = f"- [{ts}] ({source}) {text.strip()}\n"
            if not log_path.exists():
                log_path.write_text("# Owner Requests & Requirements Log\n\n", encoding="utf-8")
            with log_path.open("a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass
        # Best-effort preference auto-detect (disabled by default)
        try:
            if getattr(settings, "OWNER_PREF_AUTO_DETECT", False):
                self._auto_detect_preference(text)
        except Exception:
            pass

    def _auto_detect_preference(self, text: str) -> None:
        """Heuristic preference detection. Disabled by default."""
        raw = (text or "").strip()
        lower = raw.lower()
        if "пиши кратко" in lower or lower == "кратко":
            OwnerPreferenceModel().record_signal(
                key="style.verbosity",
                value="concise",
                signal_type="observation",
                source="owner",
                confidence_delta=0.1,
                notes="auto_detect",
            )
        if "пиши подробно" in lower or "подробно" == lower:
            OwnerPreferenceModel().record_signal(
                key="style.verbosity",
                value="verbose",
                signal_type="observation",
                source="owner",
                confidence_delta=0.1,
                notes="auto_detect",
            )
        if "на английском" in lower or "по-английски" in lower or "english only" in lower:
            OwnerPreferenceModel().record_signal(
                key="content.language",
                value="en",
                signal_type="observation",
                source="owner",
                confidence_delta=0.08,
                notes="auto_detect",
            )
        if "на русском" in lower or "по-русски" in lower:
            OwnerPreferenceModel().record_signal(
                key="content.language",
                value="ru",
                signal_type="observation",
                source="owner",
                confidence_delta=0.08,
                notes="auto_detect",
            )
        if "сначала тесты" in lower or "после тестов" in lower:
            OwnerPreferenceModel().record_signal(
                key="workflow.tests_first",
                value=True,
                signal_type="observation",
                source="owner",
                confidence_delta=0.08,
                notes="auto_detect",
            )

    def _main_keyboard(self) -> ReplyKeyboardMarkup:
        """Компактная persistent-клавиатура (6 кнопок на главном экране)."""
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("Статус"), KeyboardButton("Задачи")],
                [KeyboardButton("Создать"), KeyboardButton("Входы")],
                [KeyboardButton("Отчёт"), KeyboardButton("Еще")],
            ],
            resize_keyboard=True,
            is_persistent=True,
        )

    def set_modules(
        self,
        goal_engine=None,
        llm_router=None,
        decision_loop=None,
        agent_registry=None,
        self_healer=None,
        self_updater=None,
        conversation_engine=None,
        judge_protocol=None,
        finance=None,
        skill_registry=None,
        weekly_planner=None,
        schedule_manager=None,
        publisher_queue=None,
        cancel_state=None,
        owner_task_state=None,
    ) -> None:
        """Привязывает модули после инициализации (избегаем циклических импортов)."""
        self._goal_engine = goal_engine
        self._llm_router = llm_router
        self._decision_loop = decision_loop
        self._agent_registry = agent_registry
        if self_healer is not None:
            self._self_healer = self_healer
        if self_updater is not None:
            self._self_updater = self_updater
        if conversation_engine is not None:
            self._conversation_engine = conversation_engine
        if judge_protocol is not None:
            self._judge_protocol = judge_protocol
        if finance is not None:
            self._finance = finance
        if skill_registry is not None:
            self._skill_registry = skill_registry
        if weekly_planner is not None:
            self._weekly_planner = weekly_planner
        if schedule_manager is not None:
            self._schedule_manager = schedule_manager
        if publisher_queue is not None:
            self._publisher_queue = publisher_queue
        if cancel_state is not None:
            self._cancel_state = cancel_state
        if owner_task_state is not None:
            self._owner_task_state = owner_task_state

    # ── Запуск / Остановка ──

    async def start(self) -> None:
        """Запускает Telegram polling."""
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN не задан — бот не запущен", extra={"event": "no_token"})
            return

        self._app = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN)
            .build()
        )
        self._bot = self._app.bot

        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("help_daily", self._cmd_help_daily))
        self._app.add_handler(CommandHandler("help_rare", self._cmd_help_rare))
        self._app.add_handler(CommandHandler("help_system", self._cmd_help_system))
        self._app.add_handler(CommandHandler("main", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("goals", self._cmd_goals))
        self._app.add_handler(CommandHandler("spend", self._cmd_spend))
        self._app.add_handler(CommandHandler("approve", self._cmd_approve))
        self._app.add_handler(CommandHandler("reject", self._cmd_reject))
        self._app.add_handler(CommandHandler("goal", self._cmd_goal))
        self._app.add_handler(CommandHandler("agents", self._cmd_agents))
        # New v0.3.0 commands
        self._app.add_handler(CommandHandler("report", self._cmd_report))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))
        self._app.add_handler(CommandHandler("cancel", self._cmd_cancel))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("budget", self._cmd_budget))
        self._app.add_handler(CommandHandler("tasks", self._cmd_tasks))
        self._app.add_handler(CommandHandler("trends", self._cmd_trends))
        self._app.add_handler(CommandHandler("earnings", self._cmd_earnings))
        self._app.add_handler(CommandHandler("deep", self._cmd_deep))
        self._app.add_handler(CommandHandler("brainstorm", self._cmd_brainstorm))
        self._app.add_handler(CommandHandler("healer", self._cmd_healer))
        self._app.add_handler(CommandHandler("logs", self._cmd_logs))
        self._app.add_handler(CommandHandler("backup", self._cmd_backup))
        self._app.add_handler(CommandHandler("rollback", self._cmd_rollback))
        self._app.add_handler(CommandHandler("health", self._cmd_health))
        self._app.add_handler(CommandHandler("errors", self._cmd_errors))
        self._app.add_handler(CommandHandler("balances", self._cmd_balances))
        self._app.add_handler(CommandHandler("goals_all", self._cmd_goals_all))
        self._app.add_handler(CommandHandler("fix", self._cmd_fix))
        self._app.add_handler(CommandHandler("skills", self._cmd_skills))
        self._app.add_handler(CommandHandler("skills_pending", self._cmd_skills_pending))
        self._app.add_handler(CommandHandler("skills_audit", self._cmd_skills_audit))
        self._app.add_handler(CommandHandler("skills_fix", self._cmd_skills_fix))
        self._app.add_handler(CommandHandler("playbooks", self._cmd_playbooks))
        self._app.add_handler(CommandHandler("workflow", self._cmd_workflow))
        self._app.add_handler(CommandHandler("handoffs", self._cmd_handoffs))
        self._app.add_handler(CommandHandler("prefs", self._cmd_prefs))
        self._app.add_handler(CommandHandler("prefs_metrics", self._cmd_prefs_metrics))
        self._app.add_handler(CommandHandler("packs", self._cmd_packs))
        self._app.add_handler(CommandHandler("pubq", self._cmd_pubq))
        self._app.add_handler(CommandHandler("pubrun", self._cmd_pubrun))
        self._app.add_handler(CommandHandler("webop", self._cmd_webop))
        self._app.add_handler(CommandHandler("task_current", self._cmd_task_current))
        self._app.add_handler(CommandHandler("task_done", self._cmd_task_done))
        self._app.add_handler(CommandHandler("task_cancel", self._cmd_task_cancel))
        self._app.add_handler(CommandHandler("task_replace", self._cmd_task_replace))
        self._app.add_handler(CommandHandler("clear_goals", self._cmd_clear_goals))
        self._app.add_handler(CommandHandler("nettest", self._cmd_nettest))
        self._app.add_handler(CommandHandler("smoke", self._cmd_smoke))
        self._app.add_handler(CommandHandler("llm_mode", self._cmd_llm_mode))
        self._app.add_handler(CommandHandler("kdp_login", self._cmd_kdp_login))
        self._app.add_handler(CommandHandler("auth", self._cmd_auth))
        self._app.add_handler(
            MessageHandler(
                filters.Document.ALL | filters.PHOTO | filters.VIDEO,
                self._on_attachment,
            )
        )
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        self._app.add_error_handler(self._on_app_error)

        await self._app.initialize()
        # Ensure webhook state does not interfere with polling mode.
        try:
            await self._bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass

        # Keep Telegram menu concise; full command catalog is available via /help.
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
        # Set commands in all relevant scopes to avoid stale Telegram menu cache.
        await self._bot.set_my_commands(command_catalog, scope=BotCommandScopeDefault())
        await self._bot.set_my_commands(command_catalog, scope=BotCommandScopeAllPrivateChats())
        await self._bot.set_my_commands(command_catalog, scope=BotCommandScopeChat(chat_id=self._owner_id))

        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        logger.info("Telegram бот запущен", extra={"event": "bot_started"})
        await self.send_message("VITO запущен и готов к работе.")
        # Start file-based inbox poller (offline testing)
        if settings.OWNER_INBOX_ENABLED:
            asyncio.create_task(self._poll_owner_inbox())

    async def _on_app_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle Telegram runtime errors without crashing VITO."""
        err = getattr(context, "error", None)
        if isinstance(err, TgConflict):
            if self._telegram_conflict_mode:
                return
            self._telegram_conflict_mode = True
            logger.error(
                "Telegram polling conflict detected; switching to degraded mode (owner_inbox fallback).",
                extra={"event": "telegram_conflict_mode"},
            )
            try:
                if self._app and self._app.updater:
                    await self._app.updater.stop()
            except Exception:
                pass
            try:
                from modules.owner_inbox import write_outbox
                write_outbox(
                    "⚠️ Telegram Conflict: другой инстанс использует getUpdates. "
                    "VITO переключен в fallback owner_inbox до устранения конфликта."
                )
            except Exception:
                pass

    async def _handle_owner_text(self, text: str, source: str = "owner_inbox") -> None:
        """Process owner text without Telegram Update (offline inbox)."""
        text = (text or "").strip()
        if not text:
            return
        self._log_owner_request(text, source=source)

        async def _owner_reply(msg: str, markup=None) -> None:
            # owner_inbox path does not support inline markup; send plain text
            await self.send_message(msg)

        # Login/auth intent must win over generic status/inventory routing
        # to avoid accidental fallback into planning/research branches.
        login_svc = self._detect_service_login_request(text)
        if login_svc and self._is_inventory_prompt(text):
            self._touch_service_context(login_svc)
            if self._service_auth_confirmed.get(login_svc):
                await self.send_message(await self._format_service_inventory_snapshot(login_svc), level="result")
                return
        if await self._handle_kdp_login_flow(text, _owner_reply, with_button=False):
            self._touch_service_context("amazon_kdp")
            return
        svc = login_svc
        if svc and svc != "amazon_kdp":
            if await self._start_service_auth_flow(svc, _owner_reply, with_button=False):
                return

        lower = text.lower()
        if self._pending_service_auth and self._is_auth_done_text(lower):
            service = next(reversed(self._pending_service_auth))
            pending = self._pending_service_auth.pop(service, None) or {}
            ok, detail = await self._verify_service_auth(service)
            title, _ = self._service_auth_meta(service)
            self._touch_service_context(service)
            if ok:
                self._mark_service_auth_confirmed(service)
                await self.send_message(f"Вход подтверждён: {title}.")
            else:
                if self._requires_strict_auth_verification(service):
                    since = str(pending.get("requested_at") or "")
                    has_storage, storage_detail = self._has_cookie_storage_state(service, since_iso=since)
                    if bool(pending.get("mode") == "remote") and has_storage:
                        self._mark_service_auth_confirmed(service)
                        await self.send_message(f"Вход подтверждён: {title} (server storage захвачен, detail={storage_detail}).")
                        return
                    self._clear_service_auth_confirmed(service)
                    extra = f" {self._manual_capture_hint(service)}" if self._is_challenge_detail(detail) else ""
                    await self.send_message(self._service_needs_session_refresh_text(service, title, detail) + extra)
                elif self._is_manual_auth_service(service):
                    self._mark_service_auth_confirmed(service)
                    await self.send_message(f"Вход зафиксирован вручную: {title}. Проверка: {detail}")
                else:
                    await self.send_message(f"Не удалось подтвердить вход: {detail}")
            return

        service_inventory = self._detect_contextual_service_inventory_request(text)
        if service_inventory:
            await self.send_message(await self._format_service_inventory_snapshot(service_inventory), level="result")
            return
        service_status = self._detect_contextual_service_status_request(text)
        if service_status:
            await self.send_message(await self._format_service_auth_status_live(service_status), level="result")
            return
        if self._is_auth_issue_prompt(text):
            svc = self._last_service_context if self._has_fresh_service_context() else ""
            if svc:
                await self.send_message(await self._format_service_auth_status_live(svc), level="result")
                return

        # Accept secrets/key updates via text
        if self._try_set_env_from_text(text):
            await self.send_message("Ключ принят и сохранён. Если нужен перезапуск сервиса — скажи 'перезапусти'.")
            return
        # Explicit preference update (opt-in)
        if self._try_deactivate_preference_from_text(text):
            await self.send_message("Предпочтение деактивировано.")
            return
        if self._try_set_preference_from_text(text):
            await self.send_message("Предпочтение сохранено. Могу учитывать в будущих задачах.")
            return

        lower = text.lower()
        if self._pending_service_auth and self._is_auth_done_text(lower):
            service = next(reversed(self._pending_service_auth))
            pending = self._pending_service_auth.pop(service, None) or {}
            ok, detail = await self._verify_service_auth(service)
            title, _ = self._service_auth_meta(service)
            self._touch_service_context(service)
            if ok:
                self._mark_service_auth_confirmed(service)
                await self.send_message(f"Вход подтверждён: {title}.")
                logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text"}})
            else:
                if self._requires_strict_auth_verification(service):
                    since = str(pending.get("requested_at") or "")
                    has_storage, storage_detail = self._has_cookie_storage_state(service, since_iso=since)
                    if bool(pending.get("mode") == "remote") and has_storage:
                        self._mark_service_auth_confirmed(service)
                        await self.send_message(
                            f"Вход подтверждён: {title} (server storage захвачен, detail={storage_detail})."
                        )
                        return
                    self._clear_service_auth_confirmed(service)
                    extra = f" {self._manual_capture_hint(service)}" if self._is_challenge_detail(detail) else ""
                    await self.send_message(self._service_needs_session_refresh_text(service, title, detail) + extra)
                elif self._is_manual_auth_service(service):
                    self._mark_service_auth_confirmed(service)
                    await self.send_message(f"Вход зафиксирован вручную: {title}. Проверка: {detail}")
                    logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text_manual"}})
                else:
                    await self.send_message(f"Не удалось подтвердить вход: {detail}")
            return
        if self._pending_owner_confirmation and (self._is_yes_token(lower) or self._is_no_token(lower)):
            payload = self._pending_owner_confirmation or {}
            self._pending_owner_confirmation = None
            kind = str(payload.get("kind") or "")
            if self._is_yes_token(lower):
                if kind == "clear_goals" and self._goal_engine:
                    removed = int(self._goal_engine.clear_all_goals() or 0)
                    await self.send_message(f"Готово. Очередь целей очищена ({removed}).", level="result")
                elif kind == "rollback" and self._self_updater:
                    backup_path = str(payload.get("backup_path") or "")
                    if not backup_path:
                        await self.send_message("Нет пути к бэкапу для отката.", level="result")
                    else:
                        success = self._self_updater.rollback(backup_path)
                        status = "Откат выполнен" if success else "Ошибка отката"
                        await self.send_message(f"{status}: {backup_path}", level="result")
                else:
                    await self.send_message("Принял. Выполняю.", level="result")
            else:
                await self.send_message("Ок, отменил.", level="result")
            return
        strict_cmds = bool(getattr(settings, "TELEGRAM_STRICT_COMMANDS", True)) and not self._autonomy_max_enabled()
        if self._pending_system_action:
            if (not strict_cmds) and text.isdigit():
                actions = list((self._pending_system_action or {}).get("actions") or [])
                idx = int(text)
                if 1 <= idx <= len(actions):
                    self._pending_system_action = {"actions": [actions[idx - 1]], "origin_text": f"choice:{idx}"}
                    await self.send_message(f"Принял вариант {idx}. Запускаю.", level="result")
                    await self._execute_pending_system_action()
                    return
            if self._is_yes_token(lower):
                await self._execute_pending_system_action()
                return
            if self._is_no_token(lower):
                self._pending_system_action = None
                await self.send_message("Ок, системное действие отменено.", level="result")
                return
        # Approvals
        if self._pending_approvals:
            if self._is_yes_token(lower):
                # approve first pending
                request_id = next(iter(self._pending_approvals))
                future = self._pending_approvals.pop(request_id)
                if not future.done():
                    future.set_result(True)
                await self.send_message("Одобрено.", level="approval")
                return
            if self._is_no_token(lower):
                request_id = next(iter(self._pending_approvals))
                future = self._pending_approvals.pop(request_id)
                if not future.done():
                    future.set_result(False)
                await self.send_message("Отклонено.", level="approval")
                return

        if (not strict_cmds) and any(x in lower for x in ("llm_mode ", "режим llm", "режим lmm", "llm режим")):
            mode = "status"
            if any(x in lower for x in (" free", " тест", " gemini", " flash")):
                mode = "free"
            elif any(x in lower for x in (" prod", " боев", " production")):
                mode = "prod"
            ok, msg = self._apply_llm_mode(mode)
            await self.send_message(msg if ok else "Используй: /llm_mode free|prod|status", level="result")
            return

        service_status = self._detect_contextual_service_status_request(text)
        if service_status:
            await self.send_message(await self._format_service_auth_status_live(service_status), level="result")
            return
        service_inventory = self._detect_contextual_service_inventory_request(text)
        if service_inventory:
            await self.send_message(await self._format_service_inventory_snapshot(service_inventory), level="result")
            self._record_context_learning(
                skill_name="contextual_service_inventory_resolution",
                description=(
                    "Если активен контекст платформы, запросы вида 'проверь товары/листинги' "
                    "выполняются как проверка аккаунта этой платформы, а не как market research."
                ),
                anti_pattern=(
                    "Плохо: отправлять владельца в analyze_niche, когда он просит проверить товары в текущем аккаунте."
                ),
                method={"service": service_inventory, "source_text": text[:120]},
            )
            return

        if not strict_cmds:
            text = self._expand_short_choice(text)
            lower = text.lower()

        # Simple shortcuts
        if lower.strip() in ("/help", "help"):
            await self.send_message(self._render_help())
            return
        if lower.strip() in ("/help_daily", "help_daily", "/help daily", "help daily", "/help daily_commands"):
            await self.send_message(self._render_help("daily"))
            return
        if lower.strip() in ("/help_rare", "help_rare", "/help rare", "help rare"):
            await self.send_message(self._render_help("rare"))
            return
        if lower.strip() in ("/help_system", "help_system", "/help system", "help system"):
            await self.send_message(self._render_help("system"))
            return
        if (not strict_cmds and any(kw in lower for kw in ["статус", "/status"])) or lower.strip() in ("/status", "status"):
            await self.send_message(self._render_unified_status())
            return
        if lower.strip() in ("/workflow", "workflow"):
            try:
                from modules.workflow_state_machine import WorkflowStateMachine
                h = WorkflowStateMachine().health()
                await self.send_message(
                    f"Workflow\nВсего: {h.get('workflows_total',0)}\nОбновлён: {h.get('last_update','-')}"
                )
                return
            except Exception:
                pass
        if lower.strip() in ("/handoffs", "handoffs"):
            try:
                from modules.data_lake import DataLake
                rows = DataLake().handoff_summary(days=7)[:5]
                if not rows:
                    await self.send_message("Handoffs: нет событий за 7 дней")
                    return
                lines = ["Handoffs (7d):"]
                for r in rows:
                    lines.append(
                        f"- {r.get('from','?')} -> {r.get('to','?')}: ok={r.get('ok',0)} fail={r.get('fail',0)} total={r.get('total',0)}"
                    )
                await self.send_message("\n".join(lines))
                return
            except Exception:
                pass
        if lower.strip() in ("/prefs", "prefs", "предпочтения"):
            try:
                await self._send_prefs()
                return
            except Exception:
                pass
        if lower.strip() in ("/prefs_metrics", "prefs_metrics"):
            try:
                await self._send_prefs_metrics()
                return
            except Exception:
                pass
        if lower.strip() in ("/packs", "packs"):
            try:
                await self._send_packs()
                return
            except Exception:
                pass
        if lower.strip() in ("/task_current", "task_current"):
            if self._owner_task_state:
                active = self._owner_task_state.get_active()
                if active:
                    await self.send_message(
                        "Текущая задача владельца:\n"
                        f"- {str(active.get('text', ''))[:800]}\n"
                        f"- intent: {active.get('intent', '')}\n"
                        f"- status: {active.get('status', 'active')}",
                        level="result",
                    )
                else:
                    await self.send_message("Текущая задача не зафиксирована.", level="result")
                return
        if lower.strip() in ("/task_done", "task_done"):
            if self._owner_task_state:
                self._owner_task_state.complete(note="owner_marked_done")
                await self.send_message("Текущая задача отмечена как выполненная.", level="result")
                return
        if lower.strip() in ("/task_cancel", "task_cancel"):
            if self._owner_task_state:
                self._owner_task_state.cancel(note="owner_task_cancel")
                await self.send_message("Текущая задача отменена.", level="result")
                return
        if lower.strip().startswith("/task_replace ") or lower.strip().startswith("task_replace "):
            if self._owner_task_state:
                parts = text.split(maxsplit=1)
                if len(parts) >= 2 and parts[1].strip():
                    self._owner_task_state.set_active(parts[1].strip(), source="owner_inbox", intent="manual_replace", force=True)
                    await self.send_message("Текущая задача заменена.", level="result")
                else:
                    await self.send_message("Использование: /task_replace <новая задача>", level="result")
                return
        if lower.strip() in ("/pubq", "pubq"):
            try:
                if not self._publisher_queue:
                    await self.send_message("PublisherQueue не подключён.")
                    return
                st = self._publisher_queue.stats()
                await self.send_message(
                    f"Publish Queue\nqueued={st.get('queued',0)} running={st.get('running',0)} done={st.get('done',0)} failed={st.get('failed',0)} total={st.get('total',0)}"
                )
                return
            except Exception:
                pass
        if lower.strip().startswith("/pubrun") or lower.strip() == "pubrun":
            try:
                if not self._publisher_queue:
                    await self.send_message("PublisherQueue не подключён.")
                    return
                lim = 5
                parts = lower.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    lim = max(1, min(20, int(parts[1])))
                rows = await self._publisher_queue.process_all(limit=lim)
                await self.send_message(f"Publish run: processed={len(rows)}")
                return
            except Exception:
                pass
        if lower.strip().startswith("/webop") or lower.strip().startswith("webop"):
            try:
                if not self._agent_registry:
                    await self.send_message("AgentRegistry не подключён.")
                    return
                from modules.web_operator_pack import WebOperatorPack
                pack = WebOperatorPack(self._agent_registry)
                parts = lower.split()
                if len(parts) == 1 or parts[1] in {"list", "ls"}:
                    items = pack.list_scenarios()
                    await self.send_message("WebOp scenarios:\n" + ("\n".join(f"- {x}" for x in items) if items else "- empty"))
                    return
                if len(parts) >= 3 and parts[1] == "run":
                    res = await pack.run(parts[2], overrides={})
                    await self.send_message(f"WebOp run: {parts[2]}\nstatus={res.get('status')}\nerror={res.get('error','')}")
                    return
            except Exception:
                pass

        # Conversation engine
        if self._conversation_engine:
            try:
                if hasattr(self._conversation_engine, "set_session"):
                    self._conversation_engine.set_session("owner_inbox")
                result = await self._conversation_engine.process_message(text)
                if result.get("create_goal") and self._goal_engine:
                    from goal_engine import GoalPriority, GoalStatus
                    priority_map = {"CRITICAL": GoalPriority.CRITICAL, "HIGH": GoalPriority.HIGH,
                                    "MEDIUM": GoalPriority.MEDIUM, "LOW": GoalPriority.LOW}
                    goal = self._goal_engine.create_goal(
                        title=result.get("goal_title", text[:100]),
                        description=result.get("goal_description", text),
                        priority=priority_map.get(result.get("goal_priority", "HIGH"), GoalPriority.HIGH),
                        source="owner",
                        estimated_cost_usd=result.get("estimated_cost_usd", 0.05),
                    )
                    if result.get("needs_approval", False):
                        goal.status = GoalStatus.WAITING_APPROVAL
                        self._goal_engine._persist_goal(goal)
                    response = result.get("response", f"Цель создана: {goal.title}")
                    if result.get("needs_approval"):
                        response += "\n\nПодтверди запуск: да/нет."
                    response = self._decorate_with_numeric_hint(response, result.get("actions", []))
                    self._remember_choice_context(response)
                    await self.send_message(response, level="result")
                elif result.get("response"):
                    response = self._decorate_with_numeric_hint(result["response"], result.get("actions", []))
                    self._remember_choice_context(response)
                    await self.send_message(response, level="result")
                    if result.get("actions") and result.get("needs_confirmation"):
                        if self._autonomy_max_enabled() and self._conversation_engine:
                            out = await self._conversation_engine._execute_actions(result.get("actions", []))
                            await self.send_message(out or "Действие выполнено.", level="result")
                        else:
                            self._pending_system_action = {
                                "actions": result.get("actions", []),
                                "origin_text": text,
                            }
                else:
                    await self.send_message("Понял. Чем могу помочь?")
                return
            except Exception as e:
                logger.warning(f"ConversationEngine error: {e}", extra={"event": "conversation_error"})

        await self.send_message("Не понял: это вопрос или задача? Напиши одним предложением, что нужно сделать.")

    async def _execute_pending_system_action(self, update: Update | None = None) -> None:
        payload = self._pending_system_action or {}
        self._pending_system_action = None
        actions = payload.get("actions") or []
        if not actions:
            if update is not None:
                await update.message.reply_text("Нет действий для выполнения.", reply_markup=self._main_keyboard())
            else:
                await self.send_message("Нет действий для выполнения.", level="result")
            return
        if not self._conversation_engine:
            if update is not None:
                await update.message.reply_text("ConversationEngine не подключён.", reply_markup=self._main_keyboard())
            else:
                await self.send_message("ConversationEngine не подключён.", level="result")
            return
        try:
            out = await self._conversation_engine._execute_actions(actions)
            msg = out or "Действие выполнено."
        except Exception as e:
            msg = f"Ошибка выполнения действия: {e}"
        if update is not None:
            await self._send_response(update, msg)
        else:
            await self.send_message(msg, level="result")

    async def _poll_owner_inbox(self) -> None:
        """Poll file-based owner inbox for offline testing and fallback comms."""
        from modules.owner_inbox import read_pending_messages, mark_processed
        while True:
            try:
                for fp, text in read_pending_messages(limit=10):
                    await self._handle_owner_text(text, source="owner_inbox")
                    mark_processed(fp)
            except Exception as e:
                logger.warning(f"Owner inbox poll error: {e}", extra={"event": "owner_inbox_error"})
            await asyncio.sleep(5)

    async def stop(self) -> None:
        """Останавливает Telegram polling."""
        if self._app and self._app.updater.running:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram бот остановлен", extra={"event": "bot_stopped"})

    # ── Проверка владельца ──

    def _is_owner(self, update: Update) -> bool:
        if not update.effective_chat:
            return False
        return update.effective_chat.id == self._owner_id

    @staticmethod
    def _is_bot_sender(update: Update) -> bool:
        try:
            user = getattr(update, "effective_user", None)
            return bool(user and getattr(user, "is_bot", False))
        except Exception:
            return False

    async def _send_response(self, update: Update, text: str) -> None:
        """Send response with smart file handling.

        Detects file paths in text → reads file content and sends inline.
        Short files (<500 chars): full content in chat.
        Long files: first 500 chars + "полный текст сохранён в <relative path>".
        NEVER sends raw file paths to owner.
        """
        import re

        # Guard against unverified completion claims
        text = self._guard_outgoing(text)

        # Owner-facing chat should stay conversational by default.
        inline_paths = bool(getattr(settings, "TELEGRAM_INLINE_FILE_CONTENT", False))
        if not inline_paths:
            clean_text = self._humanize_owner_text(self._strip_technical_paths(text))
            clean_text = "\n".join(line for line in clean_text.split("\n") if line.strip())
            if clean_text:
                if len(clean_text) > 4000:
                    clean_text = clean_text[:4000] + "..."
                await update.message.reply_text(clean_text, reply_markup=self._main_keyboard())
            return

        # 1) Send binary/image files separately (no raw paths in text)
        root_rx = re.escape(str(PROJECT_ROOT))
        bin_pattern = re.compile(rf"(/(?:{root_rx}|tmp)/\S+\.(?:png|jpg|jpeg|webp|gif|pdf))")
        found_bins = bin_pattern.findall(text)
        clean_text = text
        for fp in found_bins:
            path = Path(fp)
            if path.exists():
                try:
                    await self.send_file(fp, caption=f"Файл: {path.name}")
                except Exception:
                    pass
            clean_text = clean_text.replace(f"\U0001f4ce {fp}", "")
            clean_text = clean_text.replace(fp, "")

        file_pattern = re.compile(rf"({root_rx}/\S+\.(?:txt|md|json|py|csv|log))")
        found_files = file_pattern.findall(clean_text)

        # Replace file paths with inline content in message
        for fp in found_files:
            path = Path(fp)
            replacement = ""
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        rel_path = fp.replace(str(PROJECT_ROOT) + "/", "")
                        if len(content) <= 500:
                            replacement = f"\n{content}\n"
                        else:
                            replacement = f"\n{content[:500]}...\n(полный текст: {rel_path})\n"
                except Exception:
                    pass
            # Remove "📎 /path" patterns and bare paths, insert content
            clean_text = clean_text.replace(f"\U0001f4ce {fp}", replacement)
            clean_text = clean_text.replace(fp, replacement)

        # Remove excessive empty lines
        clean_text = "\n".join(line for line in clean_text.split("\n") if line.strip())

        # Send (respect Telegram 4096 char limit)
        if clean_text:
            if len(clean_text) > 4000:
                clean_text = clean_text[:4000] + "..."
            await update.message.reply_text(clean_text, reply_markup=self._main_keyboard())

    def _strip_technical_paths(self, text: str) -> str:
        s = str(text or "")
        if not s:
            return s
        root_rx = re.escape(str(PROJECT_ROOT))
        s = re.sub(rf"{root_rx}/\S+", "[внутренний файл]", s)
        s = re.sub(r"/tmp/\S+", "[временный файл]", s)
        return s

    def _humanize_owner_text(self, text: str) -> str:
        s = str(text or "").strip()
        if not s:
            return s
        skip_tokens = (
            "request_id",
            "task_id",
            "goal_id",
            "trace_id",
            "session_id",
            "active task fixed",
            "активная задача зафиксирована",
            "workflow_session",
            "pending_approvals",
        )
        cleaned: list[str] = []
        for line in s.splitlines():
            ln = line.strip()
            low = ln.lower()
            if low.startswith("план действий:"):
                continue
            if low.startswith("вот план, что думаешь"):
                continue
            if low.startswith("план:"):
                continue
            if any(tok in low for tok in skip_tokens):
                continue
            if low.startswith("{") or low.startswith("[{") or low.startswith('"id"'):
                continue
            cleaned.append(line)
        out = "\n".join(cleaned).strip()
        out = re.sub(r"\n{3,}", "\n\n", out)
        if not out:
            return "Принял задачу в работу. Дам краткий прогресс и вернусь с результатом."
        return out

    async def _reject_stranger(self, update: Update) -> bool:
        """Отклоняет сообщения от не-владельцев."""
        if self._is_bot_sender(update):
            logger.debug(
                "Игнорирую сообщение от bot-sender",
                extra={"event": "ignore_bot_sender"},
            )
            return True
        if self._is_owner(update):
            return False
        chat_id = update.effective_chat.id if update.effective_chat else "unknown"
        logger.warning(
            f"Попытка доступа от чужого chat_id: {chat_id}",
            extra={"event": "unauthorized_access", "context": {"chat_id": chat_id}},
        )
        return True

    # ── Команды ──

    @staticmethod
    def _help_catalog() -> dict[str, Any]:
        return {
            "daily": [
                ("status", "Короткий статус VITO"),
                ("goals", "Активные цели"),
                ("goal <текст>", "Создать новую цель"),
                ("report", "Сводка: цели + финансы"),
                ("spend", "Лимит и траты за сегодня"),
                ("approve", "Одобрить ожидающий запрос"),
                ("reject", "Отклонить ожидающий запрос"),
                ("task_current", "Показать текущую owner-задачу"),
                ("task_done", "Отметить текущую задачу как выполненную"),
                ("balances", "Проверить балансы сервисов"),
            ],
            "rare": [
                ("tasks", "Задачи в выполнении"),
                ("goals_all", "История целей"),
                ("trends", "Сканер трендов"),
                ("earnings", "Доходы за 7 дней"),
                ("pubq", "Очередь публикаций"),
                ("pubrun", "Принудительно прогнать очередь публикаций"),
                ("workflow", "Состояние workflow"),
                ("handoffs", "Трассировка handoff событий"),
                ("prefs", "Предпочтения владельца"),
                ("packs", "Capability packs"),
                ("llm_mode free|prod|status", "Переключить профиль LLM"),
            ],
            "system": [
                ("cancel", "Пауза/отмена текущих задач"),
                ("resume", "Продолжить после паузы"),
                ("stop yes", "Остановить Decision Loop (с подтверждением)"),
                ("health", "Статистика SelfHealer/здоровья"),
                ("errors", "Последние ошибки"),
                ("logs", "Последние строки логов"),
                ("backup", "Сделать бэкап кода"),
                ("rollback", "Откатить последний апдейт"),
                ("clear_goals yes", "Очистить все цели (опасно)"),
                ("nettest", "Проверка сети и DNS"),
            ],
            "commands": {
                "status": ("Текущий статус ядра, бюджета и задач.", "Когда нужно понять, жив ли контур."),
                "goals": ("Показывает активные цели.", "Быстрый контроль очереди работ."),
                "goal": ("Создаёт новую цель.", "Используй: /goal <что сделать>."),
                "report": ("Сводный отчёт по системе.", "Когда нужен полный срез в одном сообщении."),
                "spend": ("Дневной расход LLM.", "Контроль токенов и бюджета."),
                "approve": ("Одобряет pending approval.", "Только если уверен в действии."),
                "reject": ("Отклоняет pending approval.", "Безопасно отклонять сомнительные запросы."),
                "cancel": ("Ставит выполнение на паузу.", "Когда нужно мгновенно остановить активность."),
                "resume": ("Возобновляет выполнение.", "После /cancel."),
                "health": ("Показывает состояние self-healing.", "Для диагностики стабильности."),
                "logs": ("Выводит последние строки логов.", "Для быстрого поиска причины ошибки."),
                "backup": ("Делает резервную копию.", "Перед рискованными изменениями."),
                "rollback": ("Откат к последнему бэкапу.", "Если последняя доработка сломала поведение."),
                "clear_goals": ("Удаляет все цели.", "Использовать только осознанно."),
                "llm_mode": ("Меняет профиль маршрутизации LLM.", "free для тестов на Gemini, prod для боевого распределения."),
            },
        }

    def _render_help(self, topic: str | None = None) -> str:
        topic_norm = str(topic or "").strip().lower()
        catalog = self._help_catalog()

        if topic_norm in {"daily", "day", "ежедневные", "daily_commands"}:
            lines = ["Ежедневные команды (часто используемые):"]
            lines.extend([f"/{cmd} — {desc}" for cmd, desc in catalog["daily"]])
            return "\n".join(lines)
        if topic_norm in {"rare", "редкие", "ops"}:
            lines = ["Редкие команды (по ситуации):"]
            lines.extend([f"/{cmd} — {desc}" for cmd, desc in catalog["rare"]])
            return "\n".join(lines)
        if topic_norm in {"system", "sys", "системные", "danger"}:
            lines = ["Системные/осторожные команды:"]
            lines.extend([f"/{cmd} — {desc}" for cmd, desc in catalog["system"]])
            lines.append("Совет: для рискованных команд сначала делай /backup.")
            return "\n".join(lines)

        cmd_key = topic_norm.lstrip("/")
        cmd_info = catalog["commands"].get(cmd_key)
        if cmd_info:
            what, when = cmd_info
            return (
                f"/{cmd_key}\n"
                f"Что делает: {what}\n"
                f"Когда использовать: {when}"
            )

        return (
            "Справка по командам VITO\n\n"
            "Разделы:\n"
            "/help_daily — ежедневные команды\n"
            "/help_rare — редкие команды\n"
            "/help_system — системные/осторожные\n\n"
            "Точечно по команде:\n"
            "/help status\n"
            "/help goal\n"
            "/help backup\n\n"
            "Быстрый старт:\n"
            "1) /status\n"
            "2) /goals\n"
            "3) /goal <что сделать>\n"
            "4) /approve или /reject"
        )

    @staticmethod
    def _help_inline_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Ежедневные", callback_data="help_topic:daily"),
                    InlineKeyboardButton("Редкие", callback_data="help_topic:rare"),
                ],
                [InlineKeyboardButton("Системные", callback_data="help_topic:system")],
            ]
        )

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        await update.message.reply_text(
            "VITO на связи.\n\n"
            "Чтобы не путаться в командах:\n"
            "/help — обзор\n"
            "/help_daily — ежедневные\n"
            "/help_rare — редкие\n"
            "/help_system — системные\n\n"
            "Быстрый старт:\n"
            "/status, /goals, /goal <текст>",
            reply_markup=self._main_keyboard(),
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        args = getattr(context, "args", None) or []
        topic = args[0] if args else None
        text = self._render_help(topic=topic)
        if topic:
            await update.message.reply_text(text, reply_markup=self._main_keyboard())
            return
        await update.message.reply_text(text, reply_markup=self._help_inline_keyboard())

    async def _cmd_help_daily(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        await update.message.reply_text(self._render_help("daily"), reply_markup=self._main_keyboard())

    async def _cmd_help_rare(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        await update.message.reply_text(self._render_help("rare"), reply_markup=self._main_keyboard())

    async def _cmd_help_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        await update.message.reply_text(self._render_help("system"), reply_markup=self._main_keyboard())

    @staticmethod
    def _render_auth_hub() -> str:
        return (
            "Входы в сервисы\n"
            "- Поддержка: Amazon KDP, Etsy, Gumroad, Printful\n"
            "- Соцсети: X/Twitter, Reddit, Threads, Instagram, Facebook, TikTok, Pinterest, YouTube, LinkedIn\n"
            "- Прочее: WordPress, Medium\n"
            "- Любой сайт: 'зайди на https://site.com' или 'зайди на site.com'\n\n"
            "После входа нажми «Я вошел» или напиши «готово»."
        )

    @staticmethod
    def _render_more_menu() -> str:
        return (
            "Дополнительно\n"
            "- /spend — расходы\n"
            "- /help — справка\n"
            "- /logs — логи\n"
            "- /health — здоровье\n"
            "- /balances — балансы"
        )

    def _render_unified_status(self, *, title: str = "VITO Status") -> str:
        snap = build_status_snapshot(
            decision_loop=self._decision_loop,
            goal_engine=self._goal_engine,
            llm_router=self._llm_router,
            finance=self._finance,
            owner_task_state=self._owner_task_state,
            pending_approvals_count=len(self._pending_approvals or {}),
        )
        return render_status_snapshot(snap, title=title)

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        await update.message.reply_text(self._render_unified_status(), reply_markup=self._main_keyboard())
        logger.info("Команда /status выполнена", extra={"event": "cmd_status"})

    async def _cmd_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        if not self._goal_engine:
            await update.message.reply_text("GoalEngine не подключён", reply_markup=self._main_keyboard())
            return

        try:
            self._goal_engine.reload_goals()
        except Exception:
            pass
        goals = self._goal_engine.get_all_goals()
        if not goals:
            await update.message.reply_text("Нет целей.", reply_markup=self._main_keyboard())
            return

        lines = []
        for g in goals[:15]:
            icon = {"completed": "done", "failed": "fail", "executing": ">>",
                    "pending": "..", "waiting_approval": "??", "planning": "~~"}.get(
                g.status.value, g.status.value
            )
            lines.append(f"[{icon}] {g.title} (${g.estimated_cost_usd:.2f})")

        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        logger.info("Команда /goals выполнена", extra={"event": "cmd_goals"})

    async def _cmd_goals_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        if not self._goal_engine:
            await update.message.reply_text("GoalEngine не подключён", reply_markup=self._main_keyboard())
            return
        try:
            self._goal_engine.reload_goals()
        except Exception:
            pass
        goals = self._goal_engine.get_all_goals(status=None)
        if not goals:
            await update.message.reply_text("Целей нет.", reply_markup=self._main_keyboard())
            return
        lines = [f"Всего целей: {len(goals)}"]
        for g in goals[:30]:
            lines.append(f"[{g.status.value}] {g.title} (${g.estimated_cost_usd:.2f})")
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())

    async def _cmd_spend(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        spend = float(self._llm_router.get_daily_spend() if self._llm_router else 0.0)
        fin_spend = float(self._finance.get_daily_spent() if self._finance else 0.0)
        limit = settings.DAILY_LIMIT_USD
        lines = [
            f"Расходы сегодня (LLM): ${spend:.2f} / ${limit:.2f}",
            f"Осталось по лимиту LLM: ${max(limit - spend, 0):.2f}",
        ]
        if fin_spend > 0:
            lines.append(f"Финконтроль (все типы расходов): ${fin_spend:.2f}")
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        logger.info("Команда /spend выполнена", extra={"event": "cmd_spend"})

    async def _cmd_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        if not self._pending_approvals:
            await update.message.reply_text("Нет запросов, ожидающих одобрения.", reply_markup=self._main_keyboard())
            return

        request_id = next(iter(self._pending_approvals))
        future = self._pending_approvals.pop(request_id)
        if not future.done():
            future.set_result(True)
        await update.message.reply_text("Одобрено.", reply_markup=self._main_keyboard())
        logger.info(
            f"Запрос одобрен: {request_id}",
            extra={"event": "approval_granted", "context": {"request_id": request_id}},
        )

    async def _cmd_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        if not self._pending_approvals:
            await update.message.reply_text("Нет запросов, ожидающих одобрения.", reply_markup=self._main_keyboard())
            return

        request_id = next(iter(self._pending_approvals))
        future = self._pending_approvals.pop(request_id)
        if not future.done():
            future.set_result(False)
        await update.message.reply_text("Отклонено.", reply_markup=self._main_keyboard())
        logger.info(
            f"Запрос отклонён: {request_id}",
            extra={"event": "approval_rejected", "context": {"request_id": request_id}},
        )

    async def _cmd_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Создание цели от владельца: /goal Заработать на Etsy шаблонах"""
        if await self._reject_stranger(update):
            return
        if not self._goal_engine:
            await update.message.reply_text("GoalEngine не подключён", reply_markup=self._main_keyboard())
            return

        text = update.message.text.removeprefix("/goal").strip()
        if not text:
            await update.message.reply_text("Использование: /goal <описание цели>", reply_markup=self._main_keyboard())
            return

        from goal_engine import GoalPriority

        goal = self._goal_engine.create_goal(
            title=text[:100],
            description=text,
            priority=GoalPriority.HIGH,
            source="owner",
        )
        if self._owner_task_state:
            try:
                self._owner_task_state.set_active(text, source="telegram", intent="goal_request", force=False)
            except Exception:
                pass
        await update.message.reply_text(
            f"Цель создана: {goal.title}\nПриоритет: HIGH.",
            reply_markup=self._main_keyboard(),
        )
        logger.info(
            f"Цель от владельца: {goal.goal_id}",
            extra={"event": "owner_goal", "context": {"goal_id": goal.goal_id, "title": text[:100]}},
        )

    async def _cmd_agents(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Список всех агентов со статусом."""
        if await self._reject_stranger(update):
            return
        if not self._agent_registry:
            await update.message.reply_text("AgentRegistry не подключён", reply_markup=self._main_keyboard())
            return

        statuses = self._agent_registry.get_all_statuses()
        if not statuses:
            await update.message.reply_text("Нет зарегистрированных агентов.", reply_markup=self._main_keyboard())
            return

        lines = [f"Агенты ({len(statuses)}):"]
        for s in statuses:
            icon = {"idle": "o", "running": ">>", "stopped": "x", "error": "!"}.get(s["status"], "?")
            lines.append(f"[{icon}] {s['name']} — {s['status']} (done:{s.get('tasks_completed', 0)}, ${s.get('total_cost', 0):.2f})")

        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        logger.info("Команда /agents выполнена", extra={"event": "cmd_agents"})

    async def _cmd_fix(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Запуск self-improve пайплайна (кодовые исправления/интеграции)."""
        if await self._reject_stranger(update):
            return
        if not self._agent_registry:
            await update.message.reply_text("AgentRegistry не подключён.", reply_markup=self._main_keyboard())
            return
        request = " ".join(context.args) if context.args else ""
        if not request:
            await update.message.reply_text(
                "Использование: /fix <что нужно исправить или интегрировать>",
                reply_markup=self._main_keyboard(),
            )
            return
        await update.message.reply_text(
            "Принято. Запускаю self-improve пайплайн (анализ → код → тесты).",
            reply_markup=self._main_keyboard(),
        )
        try:
            result = await self._agent_registry.dispatch("self_improve", step=request)
            if result and result.success:
                await update.message.reply_text("Self-improve завершён успешно.", reply_markup=self._main_keyboard())
            else:
                err = getattr(result, "error", "unknown")
                await update.message.reply_text(f"Self-improve завершён с ошибкой: {err}", reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Ошибка self-improve: {e}", reply_markup=self._main_keyboard())

    async def _cmd_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать реестр навыков."""
        if await self._reject_stranger(update):
            return
        if not self._skill_registry:
            await update.message.reply_text("SkillRegistry не подключён.", reply_markup=self._main_keyboard())
            return
        skills = self._skill_registry.list_skills(limit=20)
        if not skills:
            await update.message.reply_text("Реестр навыков пуст.", reply_markup=self._main_keyboard())
            return
        lines = ["Навыки (последние 20):"]
        for s in skills:
            lines.append(
                f"- {s['name']} | {s['status']} | accept:{s.get('acceptance_status','?')} | sec:{s['security']} | v{s['version']}"
            )
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())

    async def _cmd_skills_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать навыки, ожидающие acceptance."""
        if await self._reject_stranger(update):
            return
        if not self._skill_registry:
            await update.message.reply_text("SkillRegistry не подключён.", reply_markup=self._main_keyboard())
            return
        rows = self._skill_registry.pending_skills(limit=30)
        if not rows:
            await update.message.reply_text("Нет pending навыков.", reply_markup=self._main_keyboard())
            return
        lines = ["Pending skills (до acceptance):"]
        for r in rows:
            lines.append(f"- {r.get('name')} | {r.get('category','')} | updated:{r.get('updated_at','')}")
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())

    async def _cmd_skills_audit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Запустить аудит навыков и показать агрегированный риск-профиль."""
        if await self._reject_stranger(update):
            return
        if not self._skill_registry:
            await update.message.reply_text("SkillRegistry не подключён.", reply_markup=self._main_keyboard())
            return
        try:
            audited = self._skill_registry.audit_coverage()
            summary = self._skill_registry.audit_summary(limit=8)
            lines = [
                "Skill Audit",
                f"Проверено: {audited}",
                f"Всего: {summary.get('total', 0)}",
                f"Stable: {summary.get('stable', 0)}",
                f"Pending: {summary.get('pending', 0)}",
                f"Rejected: {summary.get('rejected', 0)}",
                f"High risk: {summary.get('high_risk', 0)}",
            ]
            risky = summary.get("top_risky", []) or []
            if risky:
                lines.append("Top risk:")
                for row in risky[:5]:
                    lines.append(
                        f"- {row.get('name')} | risk:{float(row.get('risk_score', 0.0)):.2f} | "
                        f"{row.get('compatibility')} | {row.get('acceptance_status')}"
                    )
            await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Skill audit error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_skills_fix(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Создать remediation-задачи для высокорисковых навыков."""
        if await self._reject_stranger(update):
            return
        if not self._skill_registry:
            await update.message.reply_text("SkillRegistry не подключён.", reply_markup=self._main_keyboard())
            return
        try:
            result = self._skill_registry.remediate_high_risk(limit=50)
            lines = [
                "Skill Remediation",
                f"Создано задач: {result.get('created', 0)}",
                f"Открыто задач: {result.get('open_total', 0)}",
            ]
            for item in (result.get("items", []) or [])[:5]:
                lines.append(
                    f"- {item.get('skill_name')} | {item.get('reason')} | action: {item.get('action')}"
                )
            await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Skill remediation error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_playbooks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать лучшие playbooks из verified run-ов."""
        if await self._reject_stranger(update):
            return
        try:
            from modules.playbook_registry import PlaybookRegistry
            rows = PlaybookRegistry().top(limit=20)
        except Exception:
            rows = []
        if not rows:
            await update.message.reply_text("Реестр playbooks пуст.", reply_markup=self._main_keyboard())
            return
        lines = ["Playbooks (top 20):"]
        for r in rows:
            lines.append(
                f"- {r.get('agent')}::{r.get('action')} "
                f"(ok:{r.get('success_count',0)} fail:{r.get('fail_count',0)})"
            )
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())

    async def _cmd_workflow(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать здоровье workflow и последние события по цели."""
        if await self._reject_stranger(update):
            return
        try:
            from modules.workflow_state_machine import WorkflowStateMachine
            wf = WorkflowStateMachine()
            health = wf.health()
            goal_id = " ".join(context.args).strip() if getattr(context, "args", None) else ""
            if not goal_id and self._goal_engine:
                goals = self._goal_engine.get_all_goals()
                if goals:
                    goal_id = goals[-1].goal_id
            lines = [
                "Workflow",
                f"Всего: {health.get('workflows_total', 0)}",
                f"Обновлён: {health.get('last_update', '-')}",
            ]
            if goal_id:
                lines.append(f"Goal: {goal_id}")
                events = wf.recent_events(goal_id, limit=8)
                if events:
                    for e in events:
                        lines.append(
                            f"- {e.get('created_at','')} | {e.get('from_state','')} -> {e.get('to_state','')} | {e.get('reason','')}"
                        )
                else:
                    lines.append("- Нет событий по этой цели")
            await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Workflow error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_handoffs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать сводку передач между агентами (handoff)."""
        if await self._reject_stranger(update):
            return
        try:
            from modules.data_lake import DataLake
            dl = DataLake()
            summary = dl.handoff_summary(days=7)[:10]
            recent = dl.recent_handoffs(limit=8)
            lines = ["Handoffs (7d)"]
            if summary:
                for r in summary:
                    lines.append(
                        f"- {r.get('from','?')} -> {r.get('to','?')}: ok={r.get('ok',0)} fail={r.get('fail',0)} total={r.get('total',0)}"
                    )
            else:
                lines.append("- Нет handoff событий")
            lines.append("")
            lines.append("Recent:")
            if recent:
                for r in recent[:5]:
                    lines.append(
                        f"- {r.get('created_at','')} | {r.get('from','?')} -> {r.get('to','?')} | {r.get('status','?')} | {r.get('capability','')}"
                    )
            else:
                lines.append("- Нет recent событий")
            await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Handoffs error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_prefs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать предпочтения владельца."""
        if await self._reject_stranger(update):
            return
        await self._send_prefs(reply_to=update)

    async def _cmd_prefs_metrics(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать метрики предпочтений владельца."""
        if await self._reject_stranger(update):
            return
        await self._send_prefs_metrics(reply_to=update)

    async def _send_prefs(self, reply_to: Update | None = None) -> None:
        try:
            model = OwnerPreferenceModel()
            prefs = model.list_preferences(limit=20)
            if not prefs:
                msg = "Предпочтения владельца: пока нет записей. Используй /pref ключ=значение."
            else:
                lines = ["Предпочтения владельца:"]
                for p in prefs:
                    conf = float(p.get("confidence", 0.0))
                    key = p.get("pref_key", "")
                    val = p.get("value")
                    lines.append(f"- {key}: {val} (conf={conf:.2f})")
                lines.append("Чтобы добавить: /pref ключ=значение")
                msg = "\n".join(lines)
            if reply_to is not None and getattr(reply_to, "message", None):
                await reply_to.message.reply_text(msg, reply_markup=self._main_keyboard())
            else:
                await self.send_message(msg)
        except Exception:
            if reply_to is not None and getattr(reply_to, "message", None):
                await reply_to.message.reply_text("Не удалось загрузить предпочтения.", reply_markup=self._main_keyboard())
            else:
                await self.send_message("Не удалось загрузить предпочтения.")

    async def _send_prefs_metrics(self, reply_to: Update | None = None) -> None:
        try:
            metrics = OwnerPreferenceMetrics().summary()
            lines = ["Метрики предпочтений:"]
            for k, v in metrics.items():
                lines.append(f"- {k}: {v}")
            msg = "\n".join(lines)
            if reply_to is not None and getattr(reply_to, "message", None):
                await reply_to.message.reply_text(msg, reply_markup=self._main_keyboard())
            else:
                await self.send_message(msg)
        except Exception:
            if reply_to is not None and getattr(reply_to, "message", None):
                await reply_to.message.reply_text("Не удалось загрузить метрики предпочтений.", reply_markup=self._main_keyboard())
            else:
                await self.send_message("Не удалось загрузить метрики предпочтений.")

    async def _cmd_packs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать список capability packs."""
        if await self._reject_stranger(update):
            return
        await self._send_packs(reply_to=update)

    async def _send_packs(self, reply_to: Update | None = None) -> None:
        try:
            from pathlib import Path
            root = Path(__file__).resolve().parent / "capability_packs"
            packs = []
            for spec in root.glob("*/spec.json"):
                try:
                    data = json.loads(spec.read_text(encoding="utf-8"))
                except Exception:
                    continue
                packs.append((data.get("name") or spec.parent.name, data.get("category", ""), data.get("acceptance_status", "pending")))
            if not packs:
                msg = "Capability packs: пусто."
            else:
                lines = ["Capability packs:"]
                for name, cat, status in sorted(packs):
                    lines.append(f"- {name} ({cat}) [{status}]")
                msg = "\n".join(lines)
            if reply_to is not None and getattr(reply_to, "message", None):
                await reply_to.message.reply_text(msg, reply_markup=self._main_keyboard())
            else:
                await self.send_message(msg)
        except Exception:
            if reply_to is not None and getattr(reply_to, "message", None):
                await reply_to.message.reply_text("Не удалось загрузить capability packs.", reply_markup=self._main_keyboard())
            else:
                await self.send_message("Не удалось загрузить capability packs.")

    async def _cmd_pubq(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать состояние unified publisher queue."""
        if await self._reject_stranger(update):
            return
        if not self._publisher_queue:
            await update.message.reply_text("PublisherQueue не подключён.", reply_markup=self._main_keyboard())
            return
        try:
            st = self._publisher_queue.stats()
            rows = self._publisher_queue.list_jobs(limit=10)
            lines = [
                "Publish Queue",
                f"queued={st.get('queued',0)} running={st.get('running',0)} done={st.get('done',0)} failed={st.get('failed',0)} total={st.get('total',0)}",
            ]
            for r in rows[:8]:
                lines.append(
                    f"- #{r.get('id')} {r.get('platform')} [{r.get('status')}] a={r.get('attempts',0)}/{r.get('max_attempts',0)}"
                )
            await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"PubQ error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_pubrun(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Ручной запуск обработки очереди публикаций."""
        if await self._reject_stranger(update):
            return
        if not self._publisher_queue:
            await update.message.reply_text("PublisherQueue не подключён.", reply_markup=self._main_keyboard())
            return
        limit = 5
        try:
            if context.args:
                limit = max(1, min(20, int(context.args[0])))
        except Exception:
            limit = 5
        try:
            rows = await self._publisher_queue.process_all(limit=limit)
            if not rows:
                await update.message.reply_text("Очередь пустая.", reply_markup=self._main_keyboard())
                return
            ok = sum(1 for x in rows if x.get("status") == "done")
            fail = len(rows) - ok
            await update.message.reply_text(
                f"Publish run: processed={len(rows)} done={ok} fail/retry={fail}",
                reply_markup=self._main_keyboard(),
            )
        except Exception as e:
            await update.message.reply_text(f"PubRun error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_webop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Web operator pack: list/run scenarios.

        Usage:
          /webop list
          /webop run <scenario_name>
        """
        if await self._reject_stranger(update):
            return
        if not self._agent_registry:
            await update.message.reply_text("AgentRegistry не подключён.", reply_markup=self._main_keyboard())
            return
        try:
            from modules.web_operator_pack import WebOperatorPack
            pack = WebOperatorPack(self._agent_registry)
            args = context.args or []
            if not args or args[0] in {"list", "ls"}:
                items = pack.list_scenarios()
                text = "WebOp scenarios:\n" + ("\n".join(f"- {x}" for x in items) if items else "- empty")
                await update.message.reply_text(text, reply_markup=self._main_keyboard())
                return
            if args[0] == "run":
                if len(args) < 2:
                    await update.message.reply_text("Usage: /webop run <scenario_name>", reply_markup=self._main_keyboard())
                    return
                scenario = args[1]
                res = await pack.run(scenario, overrides={})
                await update.message.reply_text(
                    f"WebOp run: {scenario}\nstatus={res.get('status')}\nerror={res.get('error','')}",
                    reply_markup=self._main_keyboard(),
                )
                return
            await update.message.reply_text("Usage: /webop list | /webop run <scenario>", reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"WebOp error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_clear_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Удалить все цели из очереди."""
        if await self._reject_stranger(update):
            return
        if not self._goal_engine:
            await update.message.reply_text("GoalEngine не подключён.", reply_markup=self._main_keyboard())
            return
        if not self._is_confirmed(getattr(context, "args", None)):
            await update.message.reply_text(
                "Подтверди удаление всех целей: `/clear_goals yes`",
                reply_markup=self._main_keyboard(),
            )
            return
        removed = self._goal_engine.clear_all_goals()
        await update.message.reply_text(
            f"Очередь целей очищена. Удалено: {removed}.",
            reply_markup=self._main_keyboard(),
        )

    async def _cmd_nettest(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Проверка сети/интернета внутри процесса VITO."""
        if await self._reject_stranger(update):
            return
        try:
            from modules.network_utils import basic_net_report
            report = basic_net_report()
            lines = ["VITO NetTest"]
            if report.get("seccomp"):
                lines.append(f"seccomp: {report['seccomp']}")
            for host, ok in report.get("dns", {}).items():
                lines.append(f"{host}: {'OK' if ok else 'FAIL'}")
            lines.append(f"overall: {'OK' if report.get('ok') else 'FAIL'}")
            await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"NetTest error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_smoke(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Manual safe smoke-check for platforms."""
        if await self._reject_stranger(update):
            return
        try:
            from modules.platform_smoke import PlatformSmoke
            # use decision loop injected platforms if available
            platforms = getattr(self._decision_loop, "_platforms", {}) if self._decision_loop else {}
            sm = PlatformSmoke(platforms)
            rows = await sm.run(names=["gumroad", "etsy", "kofi", "printful"])
            ok = sum(1 for r in rows if r.get("status") == "success")
            fail = len(rows) - ok
            lines = [f"Smoke: ok={ok}, fail={fail}"]
            for r in rows:
                lines.append(f"- {r.get('platform')}: {r.get('status')} ({r.get('detail','')})")
            await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Smoke error: {e}", reply_markup=self._main_keyboard())

    async def _cmd_llm_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Switch LLM routing mode quickly: free/prod/status."""
        if await self._reject_stranger(update):
            return
        args = list(getattr(context, "args", None) or [])
        mode = (args[0] if args else "status").strip().lower()
        ok, msg = self._apply_llm_mode(mode)
        if not ok:
            await update.message.reply_text(msg, reply_markup=self._main_keyboard())
            return
        await update.message.reply_text(msg, reply_markup=self._main_keyboard())
        logger.info("LLM mode switched", extra={"event": "llm_mode_set", "context": {"mode": mode}})

    async def _on_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Приём файлов/фото/видео от владельца и запуск document_agent."""
        if await self._reject_stranger(update):
            return
        if not update.message:
            return
        if not self._agent_registry:
            await update.message.reply_text("AgentRegistry не подключён.", reply_markup=self._main_keyboard())
            return

        attachment_dir = PROJECT_ROOT / "input" / "attachments"
        attachment_dir.mkdir(parents=True, exist_ok=True)

        file_path = None
        task_type = "document_parse"

        try:
            if update.message.document:
                doc = update.message.document
                tg_file = await doc.get_file()
                safe_name = doc.file_name or f"document_{doc.file_unique_id}"
                file_path = attachment_dir / safe_name
                await tg_file.download_to_drive(custom_path=str(file_path))
                task_type = "document_parse"
            elif update.message.photo:
                photo = update.message.photo[-1]
                tg_file = await photo.get_file()
                file_path = attachment_dir / f"photo_{photo.file_unique_id}.jpg"
                await tg_file.download_to_drive(custom_path=str(file_path))
                task_type = "image_ocr"
            elif update.message.video:
                video = update.message.video
                tg_file = await video.get_file()
                file_path = attachment_dir / f"video_{video.file_unique_id}.mp4"
                await tg_file.download_to_drive(custom_path=str(file_path))
                task_type = "video_extract"

            if not file_path:
                await update.message.reply_text("Не удалось определить тип вложения.", reply_markup=self._main_keyboard())
                return

            await update.message.reply_text(
                f"Файл получен: {file_path.name}\nНачинаю анализ.",
                reply_markup=self._main_keyboard(),
            )

            result = await self._agent_registry.dispatch(task_type, path=str(file_path))
            if not result or not result.success:
                err = getattr(result, "error", "Ошибка обработки")
                await update.message.reply_text(f"Ошибка обработки: {err}", reply_markup=self._main_keyboard())
                return

            output = result.output or {}
            extracted = ""
            if isinstance(output, dict):
                if "text" in output:
                    extracted = output.get("text") or ""
                elif "json" in output:
                    extracted = json.dumps(output.get("json"), ensure_ascii=False)[:8000]
                elif "rows" in output:
                    extracted = "\n".join([", ".join(row) for row in output.get("rows", [])])
            elif isinstance(output, str):
                extracted = output

            extracted = extracted.strip()
            caption = (update.message.caption or "").strip()
            if not extracted and caption:
                extracted = caption
            elif caption:
                extracted = caption + "\n\n" + extracted
            if not extracted:
                await update.message.reply_text("Извлечённый текст пуст.", reply_markup=self._main_keyboard())
                return
            self._log_owner_request(extracted[:2000], source=f"attachment:{file_path.name}")

            # Сохраним полный текст рядом
            out_dir = PROJECT_ROOT / "output" / "attachments"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{Path(file_path).stem}_extracted.txt"
            out_path.write_text(extracted, encoding="utf-8", errors="ignore")

            preview = extracted[:3000]
            if len(extracted) > 3000:
                preview += f"\n\n(Полный текст сохранён в {out_path.relative_to(PROJECT_ROOT)})"
            await update.message.reply_text(preview, reply_markup=self._main_keyboard())

            # Brainstorm from extracted text if applicable
            if await self._maybe_brainstorm_from_text(update, extracted):
                return

            # If conversation_engine exists, pass extracted text for natural language handling
            if self._conversation_engine:
                try:
                    if hasattr(self._conversation_engine, "set_session"):
                        sid = str(update.effective_chat.id) if update and update.effective_chat else "telegram_owner"
                        self._conversation_engine.set_session(sid)
                    await self._conversation_engine.process_message(
                        f"[Вложение:{file_path.name}]\n{extracted[:4000]}"
                    )
                except Exception:
                    pass
            logger.info(
                "Вложение обработано",
                extra={"event": "attachment_processed", "context": {"file": file_path.name, "task_type": task_type}},
            )
        except Exception as e:
            logger.error("Ошибка обработки вложения", extra={"event": "attachment_error"}, exc_info=True)
            await update.message.reply_text(f"Ошибка обработки вложения: {e}", reply_markup=self._main_keyboard())

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Произвольное текстовое сообщение от владельца → ConversationEngine."""
        if await self._reject_stranger(update):
            return

        text = update.message.text.strip()
        if not text:
            return

        self._append_telegram_trace("in", text, {"chat_id": int(self._owner_id)})

        reply_meta = self._extract_reply_context(update)
        if reply_meta:
            source = "text_reply"
        else:
            source = "text"

        self._log_owner_request(text, source=source)
        strict_cmds = bool(getattr(settings, "TELEGRAM_STRICT_COMMANDS", True)) and not self._autonomy_max_enabled()

        async def _tg_reply(msg: str, markup=None) -> None:
            kwargs = {"reply_markup": markup} if markup is not None else {"reply_markup": self._main_keyboard()}
            await update.message.reply_text(msg, **kwargs)

        # Login/auth intent must win over contextual inventory/status parsing,
        # otherwise phrases like "зайди ... проверь товары" can be misrouted.
        login_svc = self._detect_service_login_request(text)
        if login_svc and self._is_inventory_prompt(text):
            self._touch_service_context(login_svc)
            if self._service_auth_confirmed.get(login_svc):
                await update.message.reply_text(
                    await self._format_service_inventory_snapshot(login_svc),
                    reply_markup=self._main_keyboard(),
                )
                return
        if await self._handle_kdp_login_flow(text, _tg_reply, with_button=True):
            self._touch_service_context("amazon_kdp")
            return
        svc = login_svc
        if svc and svc != "amazon_kdp":
            if await self._start_service_auth_flow(svc, _tg_reply, with_button=True):
                return

        lower = text.lower()
        if self._pending_service_auth and self._is_auth_done_text(lower):
            service = next(reversed(self._pending_service_auth))
            pending = self._pending_service_auth.pop(service, None) or {}
            ok, detail = await self._verify_service_auth(service)
            title, _ = self._service_auth_meta(service)
            self._touch_service_context(service)
            if ok:
                self._mark_service_auth_confirmed(service)
                await update.message.reply_text(f"Вход подтверждён: {title}.", reply_markup=self._main_keyboard())
                logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text"}})
            else:
                if self._requires_strict_auth_verification(service):
                    since = str(pending.get("requested_at") or "")
                    has_storage, storage_detail = self._has_cookie_storage_state(service, since_iso=since)
                    if bool(pending.get("mode") == "remote") and has_storage:
                        self._mark_service_auth_confirmed(service)
                        await update.message.reply_text(
                            f"Вход подтверждён: {title} (server storage захвачен, detail={storage_detail}).",
                            reply_markup=self._main_keyboard(),
                        )
                        return
                    self._clear_service_auth_confirmed(service)
                    extra = f" {self._manual_capture_hint(service)}" if self._is_challenge_detail(detail) else ""
                    await update.message.reply_text(
                        self._service_needs_session_refresh_text(service, title, detail) + extra,
                        reply_markup=self._main_keyboard(),
                    )
                elif self._is_manual_auth_service(service):
                    self._mark_service_auth_confirmed(service)
                    await update.message.reply_text(
                        f"Вход зафиксирован вручную: {title}. Проверка: {detail}",
                        reply_markup=self._main_keyboard(),
                    )
                    logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text_manual"}})
                else:
                    await update.message.reply_text(f"Не удалось подтвердить вход: {detail}", reply_markup=self._main_keyboard())
            return

        # Highest-priority contextual routing: account inventory/status/auth issue.
        service_inventory = self._detect_contextual_service_inventory_request(text)
        if service_inventory:
            await update.message.reply_text(
                await self._format_service_inventory_snapshot(service_inventory),
                reply_markup=self._main_keyboard(),
            )
            self._record_context_learning(
                skill_name="contextual_service_inventory_resolution",
                description=(
                    "Если активен контекст платформы, запросы вида 'проверь товары/листинги' "
                    "выполняются как проверка аккаунта этой платформы, а не как market research."
                ),
                anti_pattern=(
                    "Плохо: отправлять владельца в analyze_niche, когда он просит проверить товары в текущем аккаунте."
                ),
                method={"service": service_inventory, "source_text": text[:120]},
            )
            return
        service_status = self._detect_contextual_service_status_request(text)
        if service_status:
            await update.message.reply_text(
                await self._format_service_auth_status_live(service_status),
                reply_markup=self._main_keyboard(),
            )
            self._record_context_learning(
                skill_name="contextual_service_status_resolution",
                description=(
                    "Если у владельца активный контекст платформы, короткий запрос 'статус' трактуется "
                    "как статус входа/аккаунта этой платформы."
                ),
                anti_pattern=(
                    "Плохо: игнорировать недавний контекст сервиса и отвечать системным статусом VITO "
                    "вместо статуса нужной платформы."
                ),
                method={"service": service_status, "source_text": text[:120]},
            )
            return
        if self._is_auth_issue_prompt(text):
            svc = self._last_service_context if self._has_fresh_service_context() else ""
            if svc:
                await update.message.reply_text(
                    await self._format_service_auth_status_live(svc),
                    reply_markup=self._main_keyboard(),
                )
                return

        lower = text.lower()
        if self._pending_service_auth and self._is_auth_done_text(lower):
            service = next(reversed(self._pending_service_auth))
            pending = self._pending_service_auth.pop(service, None) or {}
            ok, detail = await self._verify_service_auth(service)
            title, _ = self._service_auth_meta(service)
            self._touch_service_context(service)
            if ok:
                self._mark_service_auth_confirmed(service)
                await update.message.reply_text(f"Вход подтверждён: {title}.", reply_markup=self._main_keyboard())
                logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text"}})
            else:
                if self._requires_strict_auth_verification(service):
                    since = str(pending.get("requested_at") or "")
                    has_storage, storage_detail = self._has_cookie_storage_state(service, since_iso=since)
                    if bool(pending.get("mode") == "remote") and has_storage:
                        self._mark_service_auth_confirmed(service)
                        await update.message.reply_text(
                            f"Вход подтверждён: {title} (server storage захвачен, detail={storage_detail}).",
                            reply_markup=self._main_keyboard(),
                        )
                        return
                    self._clear_service_auth_confirmed(service)
                    extra = f" {self._manual_capture_hint(service)}" if self._is_challenge_detail(detail) else ""
                    await update.message.reply_text(
                        self._service_needs_session_refresh_text(service, title, detail) + extra,
                        reply_markup=self._main_keyboard(),
                    )
                elif self._is_manual_auth_service(service):
                    self._mark_service_auth_confirmed(service)
                    await update.message.reply_text(
                        f"Вход зафиксирован вручную: {title}. Проверка: {detail}",
                        reply_markup=self._main_keyboard(),
                    )
                    logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text_manual"}})
                else:
                    await update.message.reply_text(f"Не удалось подтвердить вход: {detail}", reply_markup=self._main_keyboard())
            return
        if self._pending_owner_confirmation and (self._is_yes_token(lower) or self._is_no_token(lower)):
            payload = self._pending_owner_confirmation or {}
            self._pending_owner_confirmation = None
            kind = str(payload.get("kind") or "")
            if self._is_yes_token(lower):
                if kind == "clear_goals" and self._goal_engine:
                    removed = int(self._goal_engine.clear_all_goals() or 0)
                    await update.message.reply_text(
                        f"Готово. Очередь целей очищена ({removed}).",
                        reply_markup=self._main_keyboard(),
                    )
                elif kind == "rollback" and self._self_updater:
                    backup_path = str(payload.get("backup_path") or "")
                    if not backup_path:
                        await update.message.reply_text(
                            "Нет пути к бэкапу для отката.",
                            reply_markup=self._main_keyboard(),
                        )
                    else:
                        success = self._self_updater.rollback(backup_path)
                        status = "Откат выполнен" if success else "Ошибка отката"
                        await update.message.reply_text(
                            f"{status}: {backup_path}",
                            reply_markup=self._main_keyboard(),
                        )
                else:
                    await update.message.reply_text("Принял. Выполняю.", reply_markup=self._main_keyboard())
            else:
                await update.message.reply_text("Ок, отменил.", reply_markup=self._main_keyboard())
            return
        if self._pending_system_action:
            if (not strict_cmds) and text.isdigit():
                actions = list((self._pending_system_action or {}).get("actions") or [])
                idx = int(text)
                if 1 <= idx <= len(actions):
                    self._pending_system_action = {"actions": [actions[idx - 1]], "origin_text": f"choice:{idx}"}
                    await update.message.reply_text(
                        f"Принял вариант {idx}. Запускаю.",
                        reply_markup=self._main_keyboard(),
                    )
                    await self._execute_pending_system_action(update)
                    return
            if self._is_yes_token(lower):
                await self._execute_pending_system_action(update)
                return
            if self._is_no_token(lower):
                self._pending_system_action = None
                await update.message.reply_text(
                    "Ок, системное действие отменено.",
                    reply_markup=self._main_keyboard(),
                )
                return
        # Pending schedule clarification (user selects which to update)
        if self._pending_schedule_update:
            sel = text.strip()
            if sel.isdigit():
                idx = int(sel)
                choices = self._pending_schedule_update.get("choices", [])
                new_sched = self._pending_schedule_update.get("new_schedule")
                mode = self._pending_schedule_update.get("mode", "update")
                if 1 <= idx <= len(choices):
                    task = choices[idx - 1]
                    try:
                        if mode == "delete":
                            self._schedule_manager.delete_task(task.id)
                            await update.message.reply_text(
                                f"Готово. Расписание #{task.id} удалено.",
                                reply_markup=self._main_keyboard(),
                            )
                        else:
                            self._schedule_manager.update_task(
                                task.id,
                                schedule_type=new_sched.schedule_type,
                                time_of_day=new_sched.time_of_day,
                                weekday=new_sched.weekday,
                                run_at=new_sched.run_at,
                            )
                            await update.message.reply_text(
                                f"Готово. Обновил расписание для задачи #{task.id}.",
                                reply_markup=self._main_keyboard(),
                            )
                    except Exception as e:
                        await update.message.reply_text(
                            f"Ошибка обновления расписания: {e}",
                            reply_markup=self._main_keyboard(),
                        )
                    self._pending_schedule_update = None
                    return
            # If not a valid selection, continue normal flow

        if not strict_cmds:
            text = self._expand_short_choice(text)
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
            self._pending_owner_confirmation = {"kind": "clear_goals", "created_at": datetime.now(timezone.utc).isoformat()}
            await update.message.reply_text(
                "Подтверди очистку всех целей: да/нет",
                reply_markup=self._main_keyboard(),
            )
            return

        # Schedule from plain text (no command required)
        if (not strict_cmds) and await self._maybe_schedule_from_text(update, text):
            return

        # Brainstorm from plain text (no command required)
        if (not strict_cmds) and await self._maybe_brainstorm_from_text(update, text):
            return

        # 0. Accept secrets/key updates via Telegram (KEY=VALUE or "set KEY=VALUE")
        if self._try_set_env_from_text(text):
            await update.message.reply_text(
                "Ключ принят и сохранён. Если нужен перезапуск сервиса — скажи 'перезапусти'.",
                reply_markup=self._main_keyboard(),
            )
            return

        # 1. Обработка нажатий persistent-кнопок (+алиасы старого меню)
        cmd = self._resolve_button_command(text)
        if cmd:
            if cmd == "help":
                await update.message.reply_text(self._render_help(), reply_markup=self._main_keyboard())
                return
            if cmd == "help_daily":
                await update.message.reply_text(self._render_help("daily"), reply_markup=self._main_keyboard())
                return
            if cmd == "help_rare":
                await update.message.reply_text(self._render_help("rare"), reply_markup=self._main_keyboard())
                return
            if cmd == "help_system":
                await update.message.reply_text(self._render_help("system"), reply_markup=self._main_keyboard())
                return
            if cmd == "auth_hub":
                await update.message.reply_text(self._render_auth_hub(), reply_markup=self._main_keyboard())
                return
            if cmd == "more":
                await update.message.reply_text(self._render_more_menu(), reply_markup=self._main_keyboard())
                return
            handler = {
                "start": self._cmd_start,
                "status": self._cmd_status,
                "goals": self._cmd_goals,
                "tasks": self._cmd_tasks,
                "report": self._cmd_report,
                "spend": self._cmd_spend,
                "approve": self._cmd_approve,
                "reject": self._cmd_reject,
            }.get(cmd)
            if handler:
                await handler(update, context)
                return
            await update.message.reply_text(
                "Отправь текст цели, и я создам её.",
                reply_markup=self._main_keyboard(),
            )
            return

        # 1.5. Natural language shortcuts (balance check, etc.)
        lower = text.strip().lower()
        if (not strict_cmds) and any(x in lower for x in ("llm_mode ", "режим llm", "режим lmm", "llm режим")):
            mode = "status"
            if any(x in lower for x in (" free", " тест", " gemini", " flash")):
                mode = "free"
            elif any(x in lower for x in (" prod", " боев", " production")):
                mode = "prod"
            ok, msg = self._apply_llm_mode(mode)
            await update.message.reply_text(
                msg if ok else "Используй: /llm_mode free|prod|status",
                reply_markup=self._main_keyboard(),
            )
            return
        if (not strict_cmds) and any(kw in lower for kw in ["баланс", "balance", "balances", "остатки", "сколько на счетах", "сколько осталось"]):
            await self._cmd_balances(update, context)
            return

        # 2. Pending approvals — да/нет/✅/❌
        if self._pending_approvals:
            if self._is_yes_token(lower):
                await self._cmd_approve(update, context)
                return
            elif self._is_no_token(lower):
                await self._cmd_reject(update, context)
                return

        # 2.5. Goal approval — approve goals in WAITING_APPROVAL status
        if self._is_yes_token(lower) and self._goal_engine:
            from goal_engine import GoalStatus
            waiting = [g for g in self._goal_engine.get_all_goals()
                       if g.status == GoalStatus.WAITING_APPROVAL]
            if waiting:
                goal = waiting[0]  # Approve the most recent waiting goal
                goal.status = GoalStatus.PENDING  # Move to PENDING so DecisionLoop picks it up
                self._goal_engine._persist_goal(goal)
                await update.message.reply_text(
                    f"✅ Одобрено: {goal.title}\nПриступаю к выполнению.",
                    reply_markup=self._main_keyboard(),
                )
                return
        elif self._is_no_token(lower) and self._goal_engine:
            from goal_engine import GoalStatus
            waiting = [g for g in self._goal_engine.get_all_goals()
                       if g.status == GoalStatus.WAITING_APPROVAL]
            if waiting:
                goal = waiting[0]
                self._goal_engine.fail_goal(goal.goal_id, "Отклонено владельцем")
                await update.message.reply_text(
                    f"❌ Отклонено: {goal.title}",
                    reply_markup=self._main_keyboard(),
                )
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

        # 3. ConversationEngine — живой разговор
        if self._conversation_engine:
            try:
                if hasattr(self._conversation_engine, "set_session"):
                    sid = str(update.effective_chat.id) if update and update.effective_chat else "telegram_owner"
                    self._conversation_engine.set_session(sid)
                result = await self._conversation_engine.process_message(text_for_engine)

                # Pass-through для команд и одобрений (обработаны выше)
                if result.get("pass_through"):
                    pass  # Уже обработано правилами выше
                elif result.get("create_goal") and self._goal_engine:
                    from goal_engine import GoalPriority, GoalStatus
                    priority_map = {"CRITICAL": GoalPriority.CRITICAL, "HIGH": GoalPriority.HIGH,
                                    "MEDIUM": GoalPriority.MEDIUM, "LOW": GoalPriority.LOW}
                    goal = self._goal_engine.create_goal(
                        title=result.get("goal_title", text[:100]),
                        description=result.get("goal_description", text),
                        priority=priority_map.get(result.get("goal_priority", "HIGH"), GoalPriority.HIGH),
                        source="owner",
                        estimated_cost_usd=result.get("estimated_cost_usd", 0.05),
                    )
                    # Approval workflow: set goal to WAITING_APPROVAL
                    if result.get("needs_approval", False):
                        goal.status = GoalStatus.WAITING_APPROVAL
                        self._goal_engine._persist_goal(goal)
                    response = result.get("response", f"Цель создана: {goal.title}")
                    if result.get("needs_approval"):
                        response += "\n\nПодтверди запуск: да/нет."
                    response = self._decorate_with_numeric_hint(response, result.get("actions", []))
                    response = self._humanize_owner_text(response)
                    self._remember_choice_context(response)
                    await update.message.reply_text(response, reply_markup=self._main_keyboard())
                elif result.get("response"):
                    response = self._decorate_with_numeric_hint(result["response"], result.get("actions", []))
                    self._remember_choice_context(response)
                    await self._send_response(update, response)
                    if result.get("actions") and result.get("needs_confirmation"):
                        if self._autonomy_max_enabled() and self._conversation_engine:
                            out = await self._conversation_engine._execute_actions(result.get("actions", []))
                            await self._send_response(update, out or "Действие выполнено.")
                        else:
                            self._pending_system_action = {
                                "actions": result.get("actions", []),
                                "origin_text": text_for_engine,
                            }
                else:
                    await update.message.reply_text(
                        "Понял. Чем могу помочь?", reply_markup=self._main_keyboard()
                    )

                logger.info(
                    f"ConversationEngine: intent={result.get('intent')}",
                    extra={"event": "conversation_processed", "context": {"intent": result.get("intent")}},
                )
                return
            except Exception as e:
                logger.warning(f"ConversationEngine error: {e}", extra={"event": "conversation_error"})

        # 4. Fallback — старое поведение
        await update.message.reply_text(
            "Не понял: это вопрос или задача? Напиши одним предложением, что нужно сделать.",
            reply_markup=self._main_keyboard(),
        )
        logger.info(
            f"Сообщение от владельца: {text[:100]}",
            extra={"event": "owner_message"},
        )

    @staticmethod
    def _extract_reply_context(update: Update) -> dict[str, str]:
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

    @staticmethod
    def _has_numbered_options(text: str) -> bool:
        import re

        lines = re.findall(r"(?m)^\s*(\d{1,2})[\.\)]\s+\S+", str(text or ""))
        return len(lines) >= 2

    def _remember_choice_context(self, response_text: str) -> None:
        if self._has_numbered_options(response_text):
            self._pending_choice_context = {"saved_at": datetime.now(timezone.utc).isoformat()}

    def _expand_short_choice(self, raw_text: str) -> str:
        text = str(raw_text or "").strip()
        if not text.isdigit():
            return text
        if not self._pending_choice_context:
            return text
        idx = int(text)
        if idx <= 0:
            return text
        self._pending_choice_context = None
        return (
            f"Выбираю вариант {idx}. Продолжай выполнять задачу автономно, "
            f"без дополнительных подтверждений, если нет критического риска."
        )

    def _decorate_with_numeric_hint(self, response: str, actions: list[dict] | None) -> str:
        text = str(response or "").strip()
        return text

    # ── Новые команды v0.3.0 ──

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Полный отчёт: финансы + цели."""
        if await self._reject_stranger(update):
            return
        parts = ["VITO Report"]
        if self._finance:
            parts.append(self._finance.format_morning_finance())
        if self._goal_engine:
            gs = self._goal_engine.get_stats()
            parts.append(
                f"Цели: {gs['completed']} выполнено, {gs['executing']} в работе, "
                f"{gs['pending']} ожидают\nУспешность: {gs['success_rate']:.0%}"
            )
        if self._owner_task_state:
            try:
                active = self._owner_task_state.get_active()
                if active:
                    parts.append(f"Текущая задача: {str(active.get('text', ''))[:200]}")
            except Exception:
                pass
        await self._send_response(update, "\n\n".join(parts))
        logger.info("Команда /report выполнена", extra={"event": "cmd_report"})

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Остановить Decision Loop."""
        if await self._reject_stranger(update):
            return
        if not self._is_confirmed(getattr(context, "args", None)):
            await update.message.reply_text(
                "Подтверди остановку цикла: `/stop yes`",
                reply_markup=self._main_keyboard(),
            )
            return
        if self._decision_loop:
            self._decision_loop.stop()
            await update.message.reply_text("Decision Loop остановлен.", reply_markup=self._main_keyboard())
        else:
            await update.message.reply_text("Decision Loop не подключён.", reply_markup=self._main_keyboard())
        logger.info("Команда /stop выполнена", extra={"event": "cmd_stop"})

    async def _cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Пауза всех текущих задач и очистка очередей."""
        if await self._reject_stranger(update):
            return
        if self._cancel_state:
            self._cancel_state.cancel(reason="owner_cancelled")
        cancelled_goals = self._cancel_goal_queue(reason="owner_cancelled")
        if self._owner_task_state:
            try:
                self._owner_task_state.cancel(note="owner_cancelled")
            except Exception:
                pass
        self._pending_approvals.clear()
        self._pending_schedule_update = None
        self._pending_owner_confirmation = None
        self._pending_choice_context = None
        if self._decision_loop:
            self._decision_loop.stop()
        await update.message.reply_text(
            f"Всё приостановлено. Отправь /resume, когда будешь готов продолжить.\n"
            f"Отменено задач из очереди: {cancelled_goals}.",
            reply_markup=self._main_keyboard(),
        )
        logger.info("Команда /cancel выполнена", extra={"event": "cmd_cancel"})

    def _cancel_goal_queue(self, reason: str = "owner_cancelled") -> int:
        if not self._goal_engine:
            return 0
        try:
            from goal_engine import GoalStatus
            terminal = {GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED}
            cancelled = 0
            for goal in self._goal_engine.get_all_goals():
                if goal.status in terminal:
                    continue
                goal.status = GoalStatus.CANCELLED
                goal.completed_at = datetime.now(timezone.utc)
                goal.results = {"cancel_reason": reason}
                self._goal_engine._persist_goal(goal)
                cancelled += 1
                try:
                    if self._decision_loop and getattr(self._decision_loop, "orchestrator", None):
                        self._decision_loop.orchestrator.cancel_session(goal.goal_id, reason=reason)
                except Exception:
                    pass
                try:
                    if self._decision_loop and getattr(self._decision_loop, "interrupts", None):
                        self._decision_loop.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="cancelled")
                except Exception:
                    pass
            return cancelled
        except Exception:
            return 0

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Возобновить Decision Loop."""
        if await self._reject_stranger(update):
            return
        if self._cancel_state:
            self._cancel_state.clear()
        if self._decision_loop and not self._decision_loop.running:
            import asyncio
            asyncio.create_task(self._decision_loop.run())
            await update.message.reply_text("Decision Loop возобновлён.", reply_markup=self._main_keyboard())
        elif self._decision_loop and self._decision_loop.running:
            await update.message.reply_text("Decision Loop уже работает.", reply_markup=self._main_keyboard())
        else:
            await update.message.reply_text("Decision Loop не подключён.", reply_markup=self._main_keyboard())
        logger.info("Команда /resume выполнена", extra={"event": "cmd_resume"})

    async def _cmd_budget(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Бюджет и P&L."""
        if await self._reject_stranger(update):
            return
        if not self._finance:
            await update.message.reply_text("FinancialController не подключён.", reply_markup=self._main_keyboard())
            return
        check = self._finance.check_expense(0)
        pnl = self._finance.get_pnl(days=30)
        text = (
            f"Бюджет\n"
            f"Сегодня: ${check.get('daily_spent', 0):.2f} / ${settings.DAILY_LIMIT_USD:.2f}\n"
            f"Осталось: ${check.get('remaining', 0):.2f}\n\n"
            f"P&L за 30 дней:\n"
            f"Расходы: ${pnl['total_expenses']:.2f}\n"
            f"Доходы: ${pnl['total_income']:.2f}\n"
            f"{'Прибыль' if pnl['profitable'] else 'Убыток'}: ${abs(pnl['net_profit']):.2f}"
        )
        await update.message.reply_text(text, reply_markup=self._main_keyboard())
        logger.info("Команда /budget выполнена", extra={"event": "cmd_budget"})

    async def _cmd_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Активные задачи."""
        if await self._reject_stranger(update):
            return
        if not self._goal_engine:
            await update.message.reply_text("GoalEngine не подключён.", reply_markup=self._main_keyboard())
            return
        from goal_engine import GoalStatus
        active_statuses = [GoalStatus.EXECUTING, GoalStatus.PENDING, GoalStatus.WAITING_APPROVAL, GoalStatus.PLANNING]
        active = []
        for status in active_statuses:
            active.extend(self._goal_engine.get_all_goals(status=status))
        if not active:
            await update.message.reply_text("Нет активных задач.", reply_markup=self._main_keyboard())
            return
        icon = {
            GoalStatus.EXECUTING: ">>",
            GoalStatus.PENDING: "..",
            GoalStatus.WAITING_APPROVAL: "??",
            GoalStatus.PLANNING: "~~",
        }
        lines = ["Активные задачи (все статусы):"]
        for g in active[:12]:
            lines.append(f"  [{icon.get(g.status, g.status.value)} {g.goal_id}] {g.title} (${g.estimated_cost_usd:.2f})")
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        logger.info("Команда /tasks выполнена", extra={"event": "cmd_tasks"})

    async def _cmd_task_current(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает текущую owner-задачу (persisted)."""
        if await self._reject_stranger(update):
            return
        if not self._owner_task_state:
            await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=self._main_keyboard())
            return
        active = self._owner_task_state.get_active()
        if not active:
            await update.message.reply_text("Текущая задача не зафиксирована.", reply_markup=self._main_keyboard())
            return
        msg = (
            "Текущая задача владельца:\n"
            f"- {str(active.get('text', ''))[:800]}\n"
            f"- intent: {active.get('intent', '')}\n"
            f"- status: {active.get('status', 'active')}"
        )
        await update.message.reply_text(msg, reply_markup=self._main_keyboard())

    async def _cmd_task_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Явно закрывает текущую owner-задачу как completed."""
        if await self._reject_stranger(update):
            return
        if not self._owner_task_state:
            await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=self._main_keyboard())
            return
        self._owner_task_state.complete(note="owner_marked_done")
        await update.message.reply_text("Текущая задача отмечена как выполненная.", reply_markup=self._main_keyboard())

    async def _cmd_task_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Явно отменяет текущую owner-задачу."""
        if await self._reject_stranger(update):
            return
        if not self._owner_task_state:
            await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=self._main_keyboard())
            return
        self._owner_task_state.cancel(note="owner_task_cancel")
        await update.message.reply_text("Текущая задача отменена.", reply_markup=self._main_keyboard())

    async def _cmd_task_replace(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Явно заменяет текущую owner-задачу новой формулировкой."""
        if await self._reject_stranger(update):
            return
        if not self._owner_task_state:
            await update.message.reply_text("OwnerTaskState не подключён.", reply_markup=self._main_keyboard())
            return
        raw = (update.message.text or "").strip()
        new_task = raw.removeprefix("/task_replace").strip()
        if not new_task:
            await update.message.reply_text(
                "Использование: /task_replace <новая задача>",
                reply_markup=self._main_keyboard(),
            )
            return
        self._owner_task_state.set_active(new_task, source="telegram", intent="manual_replace", force=True)
        await update.message.reply_text("Текущая задача заменена.", reply_markup=self._main_keyboard())

    async def _cmd_trends(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Сканирование трендов."""
        if await self._reject_stranger(update):
            return
        if not self._agent_registry:
            await update.message.reply_text("AgentRegistry не подключён.", reply_markup=self._main_keyboard())
            return
        await update.message.reply_text("Сканирую тренды...", reply_markup=self._main_keyboard())
        try:
            result = await self._agent_registry.dispatch("trend_scan")
            if result and result.success:
                output = str(result.output)[:3000]
                await update.message.reply_text(f"Тренды:\n{output}", reply_markup=self._main_keyboard())
            else:
                await update.message.reply_text("Не удалось просканировать тренды.", reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}", reply_markup=self._main_keyboard())
        logger.info("Команда /trends выполнена", extra={"event": "cmd_trends"})

    async def _cmd_earnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Доходы за 7 дней."""
        if await self._reject_stranger(update):
            return
        if not self._finance:
            await update.message.reply_text("FinancialController не подключён.", reply_markup=self._main_keyboard())
            return
        trend = self._finance.get_revenue_trend(7)
        if not trend:
            await update.message.reply_text("Нет данных о доходах за 7 дней.", reply_markup=self._main_keyboard())
            return
        lines = ["Доходы за 7 дней:"]
        for day in trend:
            lines.append(f"  {day['date']}: ${day.get('earned_usd', 0):.2f} (расход: ${day.get('spent_usd', 0):.2f})")
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        logger.info("Команда /earnings выполнена", extra={"event": "cmd_earnings"})

    async def _cmd_deep(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Глубокий анализ ниши: /deep <тема>."""
        if await self._reject_stranger(update):
            return
        text = update.message.text.removeprefix("/deep").strip()
        if not text:
            await update.message.reply_text("Использование: /deep <тема для анализа>", reply_markup=self._main_keyboard())
            return
        if not self._judge_protocol:
            await update.message.reply_text("JudgeProtocol не подключён.", reply_markup=self._main_keyboard())
            return
        # /deep brainstorm <тема> — полный brainstorm с ролями
        # /deep <тема> — быстрая оценка ниши
        if text.lower().startswith("brainstorm "):
            topic = text[len("brainstorm "):].strip()
            await update.message.reply_text(
                f"Запускаю brainstorm: {topic}\n"
                f"(Sonnet → Perplexity → GPT-5 → Opus → Perplexity → Opus, ~$0.50-0.80)",
                reply_markup=self._main_keyboard(),
            )
            try:
                result = await self._judge_protocol.brainstorm(topic)
                formatted = self._judge_protocol.format_brainstorm_for_telegram(result)
                # Split if too long for Telegram
                if len(formatted) > 4000:
                    parts = [formatted[i:i+4000] for i in range(0, len(formatted), 4000)]
                    for part in parts:
                        await update.message.reply_text(part, reply_markup=self._main_keyboard())
                else:
                    await update.message.reply_text(formatted, reply_markup=self._main_keyboard())
            except Exception as e:
                await update.message.reply_text(f"Ошибка brainstorm: {e}", reply_markup=self._main_keyboard())
        else:
            await update.message.reply_text(f"Анализирую нишу: {text}...", reply_markup=self._main_keyboard())
            try:
                verdict = await self._judge_protocol.evaluate_niche(text)
                blocks: list[str] = [self._judge_protocol.format_verdict_for_telegram(verdict)]
                # Attach richer research report if research agent is available.
                if self._agent_registry:
                    try:
                        deep_result = await self._agent_registry.dispatch(
                            "research",
                            step=text,
                            goal_title=f"Deep research: {text[:80]}",
                            content=text,
                        )
                        if deep_result and deep_result.success and deep_result.output:
                            report = str(deep_result.output).strip()
                            if report:
                                blocks.append("Детальное исследование:\n" + report)
                    except Exception as e:
                        blocks.append(f"Доп. исследование недоступно: {e}")
                formatted = "\n\n".join(blocks)
                if len(formatted) > 4000:
                    parts = [formatted[i:i+4000] for i in range(0, len(formatted), 4000)]
                    for part in parts:
                        await update.message.reply_text(part, reply_markup=self._main_keyboard())
                else:
                    await update.message.reply_text(formatted, reply_markup=self._main_keyboard())
                # Final single-owner verdict for deep research quality.
                try:
                    if self._agent_registry:
                        q = await self._agent_registry.dispatch(
                            "quality_review",
                            content=formatted[:6000],
                            content_type="deep_research_report",
                        )
                        if q and q.success and isinstance(getattr(q, "output", None), dict):
                            qout = q.output
                            q_msg = (
                                f"Финальный вердикт качества: "
                                f"{'OK' if bool(qout.get('approved', False)) else 'ПЕРЕДЕЛАТЬ'} "
                                f"(score={int(qout.get('score', 0) or 0)})."
                            )
                            await update.message.reply_text(q_msg, reply_markup=self._main_keyboard())
                except Exception:
                    pass
                if self._conversation_engine:
                    self._pending_system_action = {
                        "actions": [
                            {
                                "action": "run_product_pipeline",
                                "params": {
                                    "topic": text,
                                    "platforms": ["gumroad"],
                                    "auto_publish": False,
                                },
                            }
                        ],
                        "origin_text": f"deep:{text}",
                    }
                    await update.message.reply_text(
                        "Если ок — напиши «да», и я автоматически соберу товар под ключ (контент, SEO, legal, SMM-план, publish-пакет).",
                        reply_markup=self._main_keyboard(),
                    )
            except Exception as e:
                await update.message.reply_text(f"Ошибка анализа: {e}", reply_markup=self._main_keyboard())
        logger.info(f"Команда /deep выполнена: {text[:50]}", extra={"event": "cmd_deep"})

    async def _cmd_kdp_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Запуск browser-auth для Amazon KDP; при MFA ждёт код в следующем сообщении."""
        if await self._reject_stranger(update):
            return

        async def _reply(msg: str, markup=None) -> None:
            kwargs = {"reply_markup": markup} if markup is not None else {"reply_markup": self._main_keyboard()}
            await update.message.reply_text(msg, **kwargs)

        otp = ""
        if context and getattr(context, "args", None):
            otp = self._extract_otp_code(" ".join(context.args))
        if otp:
            self._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat()}
            await self._handle_kdp_login_flow(otp, _reply, with_button=True)
            return
        await self._handle_kdp_login_flow("зайди на amazon kdp", _reply, with_button=True)

    @staticmethod
    def _resolve_service_key(raw: str) -> str:
        s = str(raw or "").strip().lower()
        if not s:
            return ""
        if s in CommsAgent._SERVICE_CATALOG:
            return s
        for service, meta in CommsAgent._SERVICE_CATALOG.items():
            aliases = tuple(meta.get("aliases") or ())
            if s == service or s in aliases:
                return service
        return ""

    async def _cmd_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Управление входом по платформам.

        Usage:
          /auth <service> status
          /auth <service> refresh
          /auth <service> verify
          /auth etsy remote
        """
        if await self._reject_stranger(update):
            return
        args = list(getattr(context, "args", None) or [])
        if len(args) < 2:
            await update.message.reply_text(
                "Использование: /auth <service> <status|refresh|verify>\n"
                "Пример: /auth etsy refresh",
                reply_markup=self._main_keyboard(),
            )
            return
        service = self._resolve_service_key(args[0])
        action = str(args[1] or "").strip().lower()
        if not service:
            await update.message.reply_text(
                "Неизвестный сервис. Примеры: etsy, amazon_kdp, gumroad, printful, twitter, kofi, reddit.",
                reply_markup=self._main_keyboard(),
            )
            return

        async def _reply(msg: str, markup=None) -> None:
            kwargs = {"reply_markup": markup} if markup is not None else {"reply_markup": self._main_keyboard()}
            await update.message.reply_text(msg, **kwargs)

        if action == "status":
            await _reply(await self._format_service_auth_status_live(service))
            return
        if action == "refresh":
            if service == "amazon_kdp":
                await self._handle_kdp_login_flow("зайди на amazon kdp", _reply, with_button=True)
                return
            started = await self._start_service_auth_flow(service, _reply, with_button=True)
            if not started:
                title, _ = self._service_auth_meta(service)
                await _reply(f"Не удалось запустить flow входа для {title}.")
            return
        if action == "verify":
            ok, detail = await self._verify_service_auth(service)
            title, _ = self._service_auth_meta(service)
            if ok:
                self._mark_service_auth_confirmed(service)
                await _reply(f"Вход подтверждён: {title}.")
            else:
                self._clear_service_auth_confirmed(service)
                await _reply(self._service_needs_session_refresh_text(service, title, detail))
            return

        if action == "remote":
            if service not in {"etsy", "amazon_kdp", "kofi", "printful"}:
                await update.message.reply_text(
                    "Remote browser-сессия сейчас поддержана для Etsy/Amazon KDP/Ko-fi/Printful.",
                    reply_markup=self._main_keyboard(),
                )
                return
            rc, out = await self._run_remote_auth_session(service, "start")
            if rc != 0:
                await update.message.reply_text(
                    f"Не удалось запустить remote session для {service}.\n{out[:800]}",
                    reply_markup=self._main_keyboard(),
                )
                return
            await update.message.reply_text(
                "Etsy remote-сессия запущена.\n"
                f"{out[:1200]}\n"
                "Открой REMOTE_URL, введи VNC_PASSWORD, пройди вход Etsy в окне браузера, "
                "потом нажми «Я вошел» в Telegram.",
                reply_markup=self._main_keyboard(),
            )
            return

        await update.message.reply_text(
            "Неизвестное действие. Используй: status, refresh, verify или remote (для Etsy).",
            reply_markup=self._main_keyboard(),
        )

    async def _cmd_brainstorm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Мультимодельный брейншторм: /brainstorm <тема>."""
        if await self._reject_stranger(update):
            return
        if not self._judge_protocol:
            await update.message.reply_text("JudgeProtocol не подключён.", reply_markup=self._main_keyboard())
            return
        text = update.message.text.removeprefix("/brainstorm").strip()
        if not text:
            await update.message.reply_text("Использование: /brainstorm <тема>", reply_markup=self._main_keyboard())
            return
        await update.message.reply_text(
            f"Запускаю brainstorm: {text}\n"
            f"(Sonnet → Perplexity → GPT-5 → Opus → Perplexity → Opus, ~$0.50-0.80)",
            reply_markup=self._main_keyboard(),
        )
        try:
            result = await self._judge_protocol.brainstorm(text)
            formatted = self._judge_protocol.format_brainstorm_for_telegram(result)
            if len(formatted) > 4000:
                parts = [formatted[i:i+4000] for i in range(0, len(formatted), 4000)]
                for part in parts:
                    await update.message.reply_text(part, reply_markup=self._main_keyboard())
            else:
                await update.message.reply_text(formatted, reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Ошибка brainstorm: {e}", reply_markup=self._main_keyboard())
        logger.info(f"Команда /brainstorm выполнена: {text[:50]}", extra={"event": "cmd_brainstorm"})

    async def _maybe_brainstorm_from_text(self, update: Update, text: str) -> bool:
        """Detect brainstorm/weekly planning intent from plain text and run it."""
        if not self._judge_protocol:
            return False
        if not text:
            return False

        lower = text.lower()
        trigger_words = ["брейншторм", "brainstorm", "мозговой штурм"]
        plan_words = ["план", "планирование", "стратег", "strategy", "roadmap", "расписание"]
        time_words = ["недел", "week", "weekly", "месяц", "month", "monthly", "квартал", "quarter", "год", "year"]

        wants_brainstorm = any(w in lower for w in trigger_words)
        wants_week_plan = any(p in lower for p in plan_words) and any(t in lower for t in time_words)

        if not wants_brainstorm and not wants_week_plan:
            return False

        # Weekly planning request (natural text)
        if wants_week_plan and self._weekly_planner:
            await update.message.reply_text(
                "Запускаю недельное планирование и стратегический брейншторм.",
                reply_markup=self._main_keyboard(),
            )
            try:
                await self._weekly_planner()
            except Exception as e:
                await update.message.reply_text(f"Ошибка недельного планирования: {e}", reply_markup=self._main_keyboard())
            return True

        # Brainstorm request
        topic = text.strip()
        if len(topic) > 800:
            topic = topic[:800] + "…"

        await update.message.reply_text(
            f"Запускаю brainstorm: {topic}\n"
            f"(Sonnet → Perplexity → GPT-5 → Opus → Perplexity → Opus, ~$0.50-0.80)",
            reply_markup=self._main_keyboard(),
        )
        try:
            result = await self._judge_protocol.brainstorm(topic)
            formatted = self._judge_protocol.format_brainstorm_for_telegram(result)
            if len(formatted) > 4000:
                parts = [formatted[i:i+4000] for i in range(0, len(formatted), 4000)]
                for part in parts:
                    await update.message.reply_text(part, reply_markup=self._main_keyboard())
            else:
                await update.message.reply_text(formatted, reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Ошибка brainstorm: {e}", reply_markup=self._main_keyboard())
        return True

    async def _maybe_schedule_from_text(self, update: Update, text: str) -> bool:
        """Detect scheduling intent from plain text and create a scheduled task."""
        if not self._schedule_manager:
            return False
        if not text:
            return False

        from modules.schedule_parser import parse_schedule
        result = parse_schedule(text)
        if not result.ok:
            if result.needs_clarification:
                await update.message.reply_text(result.clarification or "Уточни дату/время.", reply_markup=self._main_keyboard())
                return True
            return False

        lower = text.lower()
        is_update = any(w in lower for w in ("перенеси", "перенести", "сдвинь", "измени", "изменить", "update", "reschedule", "move"))
        is_delete = any(w in lower for w in ("отмени", "удали", "удалить", "cancel", "remove"))

        # Try to find similar existing tasks
        similar = self._schedule_manager.find_similar(text, action=result.action)

        if is_delete and similar:
            # Delete the most similar (or ask if ambiguous)
            if len(similar) > 1:
                options = "\n".join([f"{i+1}. #{t.id} — {t.title}" for i, t in enumerate(similar)])
                self._pending_schedule_update = {"choices": similar, "new_schedule": None, "mode": "delete"}
                await update.message.reply_text(
                    "Уточни, какое расписание удалить:\n" + options,
                    reply_markup=self._main_keyboard(),
                )
                return True
            self._schedule_manager.delete_task(similar[0].id)
            await update.message.reply_text(
                f"Готово. Расписание #{similar[0].id} удалено.",
                reply_markup=self._main_keyboard(),
            )
            return True

        if is_update and similar:
            if len(similar) > 1:
                options = "\n".join([f"{i+1}. #{t.id} — {t.title}" for i, t in enumerate(similar)])
                self._pending_schedule_update = {"choices": similar, "new_schedule": result, "mode": "update"}
                await update.message.reply_text(
                    "Уточни, какое расписание обновить:\n" + options,
                    reply_markup=self._main_keyboard(),
                )
                return True
            self._schedule_manager.update_task(
                similar[0].id,
                schedule_type=result.schedule_type,
                time_of_day=result.time_of_day,
                weekday=result.weekday,
                run_at=result.run_at,
            )
            await update.message.reply_text(
                f"Готово. Расписание #{similar[0].id} обновлено.",
                reply_markup=self._main_keyboard(),
            )
            return True

        # If similar exists but no update intent, ask clarification
        if similar:
            options = "\n".join([f"{i+1}. #{t.id} — {t.title}" for i, t in enumerate(similar)])
            self._pending_schedule_update = {"choices": similar, "new_schedule": result, "mode": "update"}
            await update.message.reply_text(
                "Похоже, такое расписание уже есть. Обновить его?\n"
                "Ответь номером:\n" + options,
                reply_markup=self._main_keyboard(),
            )
            return True

        task_id = self._schedule_manager.add_task(
            title=result.title or text[:120],
            action=result.action or "reminder",
            schedule_type=result.schedule_type or "once",
            time_of_day=result.time_of_day,
            weekday=result.weekday,
            run_at=result.run_at,
        )

        when = ""
        if result.schedule_type == "daily":
            when = f"ежедневно в {result.time_of_day}"
        elif result.schedule_type == "weekly":
            when = f"еженедельно в {result.time_of_day}"
        elif result.schedule_type == "once":
            when = f"{result.run_at}"

        await update.message.reply_text(
            f"Готово. Поставил задачу #{task_id}: {when}.",
            reply_markup=self._main_keyboard(),
        )
        return True

    async def _cmd_healer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Статистика самолечения."""
        if await self._reject_stranger(update):
            return
        if not self._self_healer:
            await update.message.reply_text("SelfHealer не подключён.", reply_markup=self._main_keyboard())
            return
        stats = self._self_healer.get_error_stats()
        text = (
            f"SelfHealer Stats\n"
            f"Всего ошибок: {stats['total']}\n"
            f"Решено: {stats['resolved']}\n"
            f"Не решено: {stats['unresolved']}\n"
            f"Процент решения: {stats.get('resolution_rate', 0):.0%}\n"
            f"В очереди: {stats.get('pending_retries', 0)}"
        )
        await update.message.reply_text(text, reply_markup=self._main_keyboard())
        logger.info("Команда /healer выполнена", extra={"event": "cmd_healer"})

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Последние 20 строк из логов."""
        if await self._reject_stranger(update):
            return
        log_path = Path("logs/vito.log")
        if not log_path.exists():
            await update.message.reply_text("Лог-файл не найден.", reply_markup=self._main_keyboard())
            return
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()
            last_lines = lines[-20:]
            text = "".join(last_lines)[-3000:]  # Telegram limit
            await update.message.reply_text(f"Последние логи:\n{text}", reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Ошибка чтения логов: {e}", reply_markup=self._main_keyboard())
        logger.info("Команда /logs выполнена", extra={"event": "cmd_logs"})

    async def _cmd_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Создать бэкап."""
        if await self._reject_stranger(update):
            return
        if self._agent_registry:
            try:
                result = await self._agent_registry.dispatch("backup")
                if result and result.success:
                    await update.message.reply_text(f"Бэкап создан: {result.output}", reply_markup=self._main_keyboard())
                    return
            except Exception:
                pass
        if self._self_updater:
            backup_path = self._self_updater.backup_current_code()
            if backup_path:
                await update.message.reply_text(f"Бэкап создан: {backup_path}", reply_markup=self._main_keyboard())
            else:
                await update.message.reply_text("Не удалось создать бэкап.", reply_markup=self._main_keyboard())
        else:
            await update.message.reply_text("SelfUpdater не подключён.", reply_markup=self._main_keyboard())
        logger.info("Команда /backup выполнена", extra={"event": "cmd_backup"})

    async def _cmd_rollback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Откат кода."""
        if await self._reject_stranger(update):
            return
        if not self._self_updater:
            await update.message.reply_text("SelfUpdater не подключён.", reply_markup=self._main_keyboard())
            return
        history = self._self_updater.get_update_history(limit=1)
        if not history:
            await update.message.reply_text("Нет истории обновлений для отката.", reply_markup=self._main_keyboard())
            return
        last = history[0]
        backup_path = last.get("backup_path", "")
        if not backup_path:
            await update.message.reply_text("Нет бэкапа для отката.", reply_markup=self._main_keyboard())
            return
        if not self._is_confirmed(getattr(context, "args", None)):
            self._pending_owner_confirmation = {
                "kind": "rollback",
                "backup_path": backup_path,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await update.message.reply_text(
                "Откат меняет код и может удалить последние доработки.\n"
                "Подтверди: `/rollback yes` или ответь `да` на это сообщение.",
                reply_markup=self._main_keyboard(),
            )
            return
        success = self._self_updater.rollback(backup_path)
        status = "Откат выполнен" if success else "Ошибка отката"
        await update.message.reply_text(f"{status}: {backup_path}", reply_markup=self._main_keyboard())
        logger.info(f"Команда /rollback: {status}", extra={"event": "cmd_rollback"})

    async def _cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Проверка здоровья системы."""
        if await self._reject_stranger(update):
            return
        parts = ["VITO Health Check"]

        if self._decision_loop:
            st = self._decision_loop.get_status()
            parts.append(f"Decision Loop: {'OK' if st['running'] else 'STOPPED'}")

        if self._agent_registry:
            try:
                result = await self._agent_registry.dispatch("health_check")
                parts.append(f"Health: {result.output if result and result.success else 'N/A'}")
            except Exception:
                parts.append("Health dispatch: N/A")

        if self._llm_router:
            parts.append(f"LLM spend today: ${self._llm_router.get_daily_spend():.2f}")
            parts.append(f"Daily limit OK: {self._llm_router.check_daily_limit()}")

        agents_count = len(self._agent_registry.get_all_statuses()) if self._agent_registry else 0
        parts.append(f"Agents: {agents_count}")

        await update.message.reply_text("\n".join(parts), reply_markup=self._main_keyboard())
        logger.info("Команда /health выполнена", extra={"event": "cmd_health"})

    async def _cmd_errors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Последние нерешённые ошибки."""
        if await self._reject_stranger(update):
            return
        if not self._self_healer:
            await update.message.reply_text("SelfHealer не подключён.", reply_markup=self._main_keyboard())
            return
        stats = self._self_healer.get_error_stats()
        recent = stats.get("recent", [])
        unresolved = [e for e in recent if not e.get("resolved")][:10]
        if not unresolved:
            await update.message.reply_text("Нет нерешённых ошибок.", reply_markup=self._main_keyboard())
            return
        lines = ["Нерешённые ошибки:"]
        for e in unresolved:
            lines.append(f"  [{e.get('module', '?')}] {e.get('error_type', '?')}: {e.get('message', '?')[:80]}")
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        logger.info("Команда /errors выполнена", extra={"event": "cmd_errors"})

    async def _cmd_balances(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check balances across all external services."""
        if await self._reject_stranger(update):
            return
        await update.message.reply_text("Проверяю балансы...", reply_markup=self._main_keyboard())
        try:
            from modules.balance_checker import BalanceChecker
            text = (update.message.text or "").lower()
            show_env_keys = any(x in text for x in ("env", "keys", "raw"))
            checker = BalanceChecker()
            balances = await checker.check_all(include_env_keys=show_env_keys)

            # Add internal VITO spend data
            internal = {}
            if self._finance:
                internal["daily_spent"] = self._finance.get_daily_spent()
                internal["daily_earned"] = self._finance.get_daily_earned()
                internal["daily_limit"] = settings.DAILY_LIMIT_USD

            report = checker.format_report(balances, include_internal=internal, show_env_keys=show_env_keys)
            await update.message.reply_text(report, reply_markup=self._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Ошибка проверки балансов: {e}", reply_markup=self._main_keyboard())
        logger.info("Команда /balances выполнена", extra={"event": "cmd_balances"})

    # ── Inline callback ──

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка нажатий inline-кнопок одобрения."""
        query = update.callback_query
        if not query or not query.data:
            return

        # Проверка владельца
        if query.from_user.id != self._owner_id:
            await query.answer("Доступ запрещён", show_alert=True)
            return

        parts = query.data.split(":", 1)
        if len(parts) != 2:
            await query.answer("Неизвестная команда")
            return

        action, request_id = parts

        if action == "help_topic":
            topic = str(request_id or "").strip().lower()
            await query.answer("Открываю")
            text = self._render_help(topic if topic in {"daily", "rare", "system"} else None)
            await self._safe_edit_callback_message(query, text)
            return

        if action == "auth_cancel":
            self._pending_service_auth.pop(request_id, None)
            await query.answer("Отменено")
            await self._safe_edit_callback_message(query, f"{query.message.text}\n\n— Отменено")
            return

        if action == "auth_done":
            service = str(request_id or "").strip().lower()
            pending = self._pending_service_auth.pop(service, None) or {}
            self._touch_service_context(service)
            try:
                ok, detail = await self._verify_service_auth(service)
            except Exception as e:
                ok, detail = False, f"Ошибка проверки авторизации: {e}"
            title, _ = self._service_auth_meta(service)
            if ok:
                stamp = datetime.now(timezone.utc).isoformat()
                self._service_auth_confirmed[service] = stamp
                self._save_auth_state()
                label = f"Вход подтверждён: {title}"
                await query.answer("Вход подтверждён")
                await self._safe_edit_callback_message(query, f"{query.message.text}\n\n— {label}")
                logger.info(
                    f"Inline auth_done: {service}",
                    extra={"event": "inline_auth_done", "context": {"service": service, "mode": "verified"}},
                )
                await self.send_message(label, level="result")
                return
            # Fallback: for browser/manual flows keep owner's explicit confirmation,
            # but clearly mark that technical probe failed.
            if self._requires_strict_auth_verification(service):
                since = str(pending.get("requested_at") or "")
                has_storage, storage_detail = self._has_cookie_storage_state(service, since_iso=since)
                if bool(pending.get("mode") == "remote") and has_storage:
                    stamp = datetime.now(timezone.utc).isoformat()
                    self._service_auth_confirmed[service] = stamp
                    self._save_auth_state()
                    label = f"Вход подтверждён: {title} (server storage захвачен)"
                    await query.answer("Вход подтверждён")
                    await self._safe_edit_callback_message(query, f"{query.message.text}\n\n— {label}\n({storage_detail})")
                    await self.send_message(label, level="result")
                    return
                self._clear_service_auth_confirmed(service)
                extra = f" {self._manual_capture_hint(service)}" if self._is_challenge_detail(detail) else ""
                await query.answer("Нужно обновить сессию", show_alert=False)
                await self._safe_edit_callback_message(query, f"{query.message.text}\n\n— Нужно обновить сессию.\n{detail}{extra}")
                await self.send_message(self._service_needs_session_refresh_text(service, title, detail) + extra, level="warning")
                return
            if self._is_manual_auth_service(service):
                stamp = datetime.now(timezone.utc).isoformat()
                self._service_auth_confirmed[service] = stamp
                self._save_auth_state()
                label = f"Вход зафиксирован вручную: {title}"
                await query.answer("Принято")
                await self._safe_edit_callback_message(query, f"{query.message.text}\n\n— {label}\n(Проверка: {detail})")
                logger.info(
                    f"Inline auth_done: {service}",
                    extra={"event": "inline_auth_done", "context": {"service": service, "mode": "manual_fallback", "detail": detail[:200]}},
                )
                await self.send_message(f"{label}. Можно продолжать работу.", level="result")
                return
            await query.answer("Не подтверждено", show_alert=True)
            await self._safe_edit_callback_message(query, f"{query.message.text}\n\n— Вход не подтверждён.\n{detail}")
            await self.send_message(f"Не удалось подтвердить вход: {title}. Деталь: {detail}", level="warning")
            return

        future = self._pending_approvals.pop(request_id, None)
        if future is None:
            await query.answer("Запрос уже обработан или не найден")
            await query.edit_message_reply_markup(reply_markup=None)
            return

        approved = action == "approve"
        if not future.done():
            future.set_result(approved)

        label = "Одобрено" if approved else "Отклонено"
        await query.answer(label)
        await self._safe_edit_callback_message(query, f"{query.message.text}\n\n— {label}")

        logger.info(
            f"Inline {label.lower()}: {request_id}",
            extra={"event": f"inline_{'approved' if approved else 'rejected'}",
                   "context": {"request_id": request_id}},
        )

    async def _safe_edit_callback_message(self, query, text: str) -> None:
        """Best-effort callback message edit; do not interrupt flow if edit is rejected."""
        try:
            await query.edit_message_text(text=text)
        except TgBadRequest:
            logger.info(
                "Callback message edit skipped (non-editable or unchanged).",
                extra={"event": "callback_edit_skipped"},
            )
        except Exception:
            logger.warning(
                "Callback message edit failed unexpectedly.",
                extra={"event": "callback_edit_failed"},
                exc_info=True,
            )

    # ── API для других модулей ──

    def _inline_file_paths(self, text: str) -> str:
        """Replace file paths in text with inline content.

        Short files (<500 chars): full content.
        Long files: first 500 chars + relative path reference.
        """
        import re

        root_rx = re.escape(str(PROJECT_ROOT))
        file_pattern = re.compile(rf"({root_rx}/\S+\.(?:txt|md|json|py|csv|log))")
        found = file_pattern.findall(text)
        if not found:
            return text

        result = text
        for fp in found:
            path = Path(fp)
            replacement = ""
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        rel_path = fp.replace(str(PROJECT_ROOT) + "/", "")
                        if len(content) <= 500:
                            replacement = f"\n{content}\n"
                        else:
                            replacement = f"\n{content[:500]}...\n(полный текст: {rel_path})\n"
                except Exception:
                    pass
            result = result.replace(f"\U0001f4ce {fp}", replacement)
            result = result.replace(fp, replacement)

        return "\n".join(line for line in result.split("\n") if line.strip())

    def _should_send(self, text: str, level: str) -> bool:
        """Notification policy to reduce spam."""
        import os
        if (level or "").lower() == "cron":
            if not bool(getattr(settings, "TELEGRAM_CRON_ENABLED", False)):
                return False
            try:
                if self._cancel_state and self._cancel_state.is_cancelled():
                    return False
            except Exception:
                pass
            return True
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True
        mode = (self._notify_mode or "minimal").lower()
        if mode == "all":
            return True
        # minimal: only critical/approval/result
        if level in ("critical", "approval", "result"):
            return True
        # Allow explicit user-facing reports
        if any(kw in text.lower() for kw in ["отчёт", "report", "готово", "готов", "результат"]):
            return True
        return False

    def _try_set_preference_from_text(self, text: str) -> bool:
        """Parse explicit preference commands and store in OwnerPreferenceModel.

        Supported:
        - /pref key=value
        - pref key = value
        - preference: key=value
        - предпочтение: key=value
        - remember: key=value
        """
        raw = (text or "").strip()
        if not raw:
            return False
        lower = raw.lower()
        if not (
            lower.startswith("/pref")
            or lower.startswith("pref ")
            or lower.startswith("pref:")
            or lower.startswith("preference:")
            or lower.startswith("предпочтение:")
            or lower.startswith("remember:")
        ):
            return False

        payload = raw
        for prefix in ("/pref", "pref:", "pref ", "preference:", "предпочтение:", "remember:"):
            if lower.startswith(prefix):
                payload = raw[len(prefix):].strip()
                break
        if "=" not in payload:
            return False
        key, value = payload.split("=", 1)
        key = key.strip()
        if not key:
            return False
        value = value.strip()
        if not value:
            return False

        parsed_value = _parse_pref_value(value)
        try:
            OwnerPreferenceModel().set_preference(
                key=key,
                value=parsed_value,
                source="owner",
                confidence=1.0,
                notes="explicit owner preference",
            )
            try:
                DataLake().record(
                    agent="comms_agent",
                    task_type="owner_preference_set",
                    status="success",
                    output={"key": key, "value": parsed_value},
                    source="owner",
                )
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _try_deactivate_preference_from_text(self, text: str) -> bool:
        """Parse preference removal commands.

        Supported:
        - /pref_del key
        - /pref_remove key
        - forget key
        - забыть key
        """
        raw = (text or "").strip()
        if not raw:
            return False
        lower = raw.lower()
        prefixes = ("/pref_del", "/pref_remove", "forget ", "забыть ")
        if not any(lower.startswith(p) for p in prefixes):
            return False
        for p in prefixes:
            if lower.startswith(p):
                key = raw[len(p):].strip()
                break
        else:
            key = ""
        if not key:
            return False
        try:
            OwnerPreferenceModel().deactivate_preference(key, notes="owner_request")
            try:
                DataLake().record(
                    agent="comms_agent",
                    task_type="owner_preference_deactivate",
                    status="success",
                    output={"key": key},
                    source="owner",
                )
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _guard_outgoing(self, text: str) -> str:
        """Prevent unverified completion claims in outbound messages."""
        try:
            from modules.fact_gate import gate_outgoing_claim
            decision = gate_outgoing_claim(text, evidence_hours=24)
            if not decision.allowed:
                return decision.text
        except Exception:
            return "Это было предложение/план, а не подтверждённый факт выполнения. Нужна команда на запуск?"
        return text

    async def send_message(self, text: str, level: str = "info") -> bool:
        """Отправляет сообщение владельцу. File paths auto-inlined."""
        if not self._bot:
            logger.warning("Бот не запущен — сообщение не отправлено", extra={"event": "send_no_bot"})
            # Offline fallback to owner outbox
            try:
                from modules.owner_inbox import write_outbox
                write_outbox(text)
                return True
            except Exception:
                return False
        try:
            if not self._should_send(text, level):
                logger.debug("Сообщение подавлено политикой уведомлений", extra={"event": "message_suppressed"})
                return True
            guarded = self._guard_outgoing(text)
            inline_paths = bool(getattr(settings, "TELEGRAM_INLINE_FILE_CONTENT", False))
            clean = self._inline_file_paths(guarded) if inline_paths else self._humanize_owner_text(self._strip_technical_paths(guarded))
            if len(clean) > 4000:
                clean = clean[:4000] + "..."
            await self._bot.send_message(chat_id=self._owner_id, text=clean)
            self._append_telegram_trace("out", clean, {"chat_id": int(self._owner_id), "level": str(level or "info")})
            logger.info(
                f"Сообщение отправлено ({len(clean)} символов)",
                extra={"event": "message_sent", "context": {"length": len(clean)}},
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}", extra={"event": "send_failed"}, exc_info=True)
            # Fallback via curl+--resolve if DNS broken
            try:
                from modules.telegram_fallback import send_message as fb_send
                token = getattr(self._bot, "token", "") if self._bot else ""
                if token and self._owner_id:
                    ok = fb_send(token, str(self._owner_id), clean if 'clean' in locals() else text)
                    if ok:
                        logger.info("Fallback Telegram send ok", extra={"event": "send_fallback_ok"})
                        return True
            except Exception:
                pass
            # Offline fallback to owner outbox
            try:
                from modules.owner_inbox import write_outbox
                write_outbox(clean if 'clean' in locals() else text)
                return True
            except Exception:
                pass
            return False

    async def send_file(self, file_path: str, caption: str = "") -> bool:
        """Отправляет файл владельцу (для превью продуктов)."""
        if not self._bot:
            # Offline fallback: write outbox note
            try:
                from modules.owner_inbox import write_outbox
                write_outbox(f"Файл готов: {file_path}\n{caption}")
                return True
            except Exception:
                return False
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Файл не найден: {file_path}", extra={"event": "file_not_found"})
            return False
        try:
            safe_caption = self._guard_outgoing(caption) if caption else ""
            with open(path, "rb") as f:
                await self._bot.send_document(
                    chat_id=self._owner_id, document=f, caption=safe_caption[:1024]
                )
            logger.info(
                f"Файл отправлен: {path.name}",
                extra={"event": "file_sent", "context": {"file": path.name}},
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}", extra={"event": "file_send_failed"}, exc_info=True)
            # Fallback via curl+--resolve if DNS broken
            try:
                from modules.telegram_fallback import send_document as fb_doc
                token = getattr(self._bot, "token", "") if self._bot else ""
                if token and self._owner_id:
                    safe_caption = self._guard_outgoing(caption) if caption else ""
                    ok = fb_doc(token, str(self._owner_id), str(path), caption=safe_caption[:1024])
                    if ok:
                        logger.info("Fallback Telegram file ok", extra={"event": "file_send_fallback_ok"})
                        return True
            except Exception:
                pass
            # Offline fallback
            try:
                from modules.owner_inbox import write_outbox
                write_outbox(f"Файл готов: {file_path}\n{caption}")
                return True
            except Exception:
                pass
            return False

    async def request_approval(
        self, request_id: str, message: str, timeout_seconds: int = 3600
    ) -> Optional[bool]:
        """Запрашивает одобрение у владельца. Возвращает True/False/None (timeout)."""
        import os
        if os.getenv("AUTO_APPROVE_TESTS") == "1":
            logger.info(
                "Auto-approve enabled for tests",
                extra={"event": "approval_auto", "context": {"request_id": request_id}},
            )
            if timeout_seconds <= 0:
                return None
            return True

        # Anti-spam gate for repetitive publish approvals (e.g. publish_twitter_*)
        channel = self._approval_channel(request_id)
        if channel:
            cooldown_sec = int(getattr(settings, "APPROVAL_REPEAT_COOLDOWN_SEC", 1800) or 1800)
            # If same channel is already pending, suppress duplicate prompt.
            if any(str(k).lower().startswith(f"{channel}_") for k in (self._pending_approvals or {}).keys()):
                logger.info(
                    "Approval suppressed: channel already pending",
                    extra={"event": "approval_suppressed_pending", "context": {"request_id": request_id, "channel": channel}},
                )
                return None
            last_iso = str(self._approval_last_sent_at.get(channel, "") or "").strip()
            if last_iso:
                try:
                    last_dt = datetime.fromisoformat(last_iso)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    if age < max(60, cooldown_sec):
                        logger.info(
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
        self._pending_approvals[request_id] = future
        if channel:
            self._approval_last_sent_at[channel] = datetime.now(timezone.utc).isoformat()

        inline_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Одобрить", callback_data=f"approve:{request_id}"),
                InlineKeyboardButton("Отклонить", callback_data=f"reject:{request_id}"),
            ]
        ])
        if self._bot:
            try:
                await self._bot.send_message(
                    chat_id=self._owner_id,
                    text=message,
                    reply_markup=inline_kb,
                )
            except Exception:
                await self.send_message(message, level="approval")
        else:
            await self.send_message(message, level="approval")

        logger.info(
            f"Запрос одобрения: {request_id}",
            extra={"event": "approval_requested", "context": {"request_id": request_id}},
        )

        if timeout_seconds <= 0:
            self._pending_approvals.pop(request_id, None)
            logger.warning(
                f"Таймаут одобрения: {request_id}",
                extra={"event": "approval_timeout", "context": {"request_id": request_id}},
            )
            return None

        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
            return result
        except asyncio.TimeoutError:
            self._pending_approvals.pop(request_id, None)
            logger.warning(
                f"Таймаут одобрения: {request_id}",
                extra={"event": "approval_timeout", "context": {"request_id": request_id}},
            )
            return None

    async def request_approval_with_files(
        self,
        request_id: str,
        message: str,
        files: list[str],
        timeout_seconds: int = 3600,
    ) -> Optional[bool]:
        """Запрашивает одобрение и отправляет файлы-превью до запроса."""
        sent_any = False
        for fp in files:
            try:
                await self.send_file(fp, caption=f"Превью: {Path(fp).name}")
                sent_any = True
            except Exception:
                continue
        if not sent_any and files:
            message = message + "\n(ВНИМАНИЕ: файлы превью не отправлены.)"
        return await self.request_approval(request_id=request_id, message=message, timeout_seconds=timeout_seconds)

    async def send_morning_report(self, report: str) -> bool:
        """Отправляет утренний отчёт."""
        return await self.send_message(report, level="result")

    def pending_approvals_count(self) -> int:
        """Return count of pending approvals in comms layer."""
        return len(self._pending_approvals or {})

    def pending_approvals_list(self) -> list[str]:
        """Return pending approval request ids."""
        try:
            return list(self._pending_approvals.keys())
        except Exception:
            return []

    async def notify_error(self, module: str, error: str) -> bool:
        """Уведомляет владельца о критической ошибке."""
        return await self.send_message(
            f"VITO Error | {module}\n{error}",
            level="critical",
        )


def _parse_pref_value(raw: str):
    raw = raw.strip()
    if not raw:
        return ""
    if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith("[") and raw.endswith("]")):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    low = raw.lower()
    if low in ("true", "yes", "да", "on"):
        return True
    if low in ("false", "no", "нет", "off"):
        return False
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except Exception:
        return raw
