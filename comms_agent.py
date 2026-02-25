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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from telegram import (
    Bot,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
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
from config.settings import settings
from modules.owner_preference_model import OwnerPreferenceModel
from modules.data_lake import DataLake

logger = get_logger("comms_agent", agent="comms_agent")


class CommsAgent:
    def __init__(self):
        self._bot: Optional[Bot] = None
        self._app: Optional[Application] = None
        self._owner_id: int = int(settings.TELEGRAM_OWNER_CHAT_ID)
        self._notify_mode: str = getattr(settings, "NOTIFY_MODE", "minimal")

        # Очередь запросов на одобрение: request_id → asyncio.Future
        self._pending_approvals: dict[str, asyncio.Future] = {}
        # Ожидаем уточнение по расписанию
        self._pending_schedule_update: dict | None = None
        self._telegram_conflict_mode: bool = False

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

        # Маппинг текста кнопок → имена команд
        self._button_map: dict[str, str] = {
            "Статус": "status",
            "Цели": "goals",
            "Расходы": "spend",
            "Одобрить": "approve",
            "Отклонить": "reject",
            "Новая цель": "goal",
        }

        logger.info("CommsAgent инициализирован", extra={"event": "init"})

    def _try_set_env_from_text(self, text: str) -> bool:
        """Parse KEY=VALUE messages and save to .env (owner only)."""
        import os
        import re
        from pathlib import Path

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
            "ETSY_KEYSTRING", "ETSY_SHARED_SECRET", "KOFI_API_KEY", "KOFI_PAGE_ID",
            "REPLICATE_API_TOKEN", "ANTICAPTCHA_KEY",
            "TWITTER_BEARER_TOKEN", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET",
            "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
            "THREADS_ACCESS_TOKEN", "THREADS_USER_ID",
            "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD", "REDDIT_USER_AGENT",
            "TIKTOK_ACCESS_TOKEN",
        }
        if key not in allowed:
            return False

        env_path = Path("/home/vito/vito-agent/.env")
        text_env = env_path.read_text() if env_path.exists() else ""
        if re.search(rf"^{key}=.*$", text_env, flags=re.M):
            text_env = re.sub(rf"^{key}=.*$", f"{key}={value}", text_env, flags=re.M)
        else:
            if text_env and not text_env.endswith("\n"):
                text_env += "\n"
            text_env += f"{key}={value}\n"
        env_path.write_text(text_env)

        # Update process env + settings if present
        os.environ[key] = value
        try:
            from config.settings import settings
            if hasattr(settings, key):
                setattr(settings, key, value)
        except Exception:
            pass
        logger.info("Env key set via Telegram", extra={"event": "env_set", "context": {"key": key}})
        return True

    def _log_owner_request(self, text: str, source: str = "text") -> None:
        """Append owner requests to requirements log with timestamp."""
        try:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).isoformat()
            log_path = Path("/home/vito/vito-agent/docs/OWNER_REQUIREMENTS_LOG.md")
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

    def _main_keyboard(self) -> ReplyKeyboardMarkup:
        """Persistent-клавиатура с основными командами."""
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("Статус"), KeyboardButton("Цели")],
                [KeyboardButton("Расходы"), KeyboardButton("Одобрить")],
                [KeyboardButton("Отклонить"), KeyboardButton("Новая цель")],
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
        self._app.add_handler(CommandHandler("pubq", self._cmd_pubq))
        self._app.add_handler(CommandHandler("pubrun", self._cmd_pubrun))
        self._app.add_handler(CommandHandler("webop", self._cmd_webop))
        self._app.add_handler(CommandHandler("clear_goals", self._cmd_clear_goals))
        self._app.add_handler(CommandHandler("nettest", self._cmd_nettest))
        self._app.add_handler(CommandHandler("smoke", self._cmd_smoke))
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

        await self._bot.set_my_commands([
            BotCommand("status", "Статус системы"),
            BotCommand("goals", "Активные цели"),
            BotCommand("spend", "Расходы за сегодня"),
            BotCommand("approve", "Одобрить запрос"),
            BotCommand("reject", "Отклонить запрос"),
            BotCommand("goal", "Создать цель"),
            BotCommand("agents", "Список агентов"),
            BotCommand("report", "Полный отчёт"),
            BotCommand("stop", "Остановить Decision Loop"),
            BotCommand("resume", "Возобновить Decision Loop"),
            BotCommand("budget", "Бюджет и P&L"),
            BotCommand("tasks", "Активные задачи"),
            BotCommand("trends", "Сканирование трендов"),
            BotCommand("earnings", "Доходы за 7 дней"),
            BotCommand("deep", "Глубокий анализ ниши"),
            BotCommand("healer", "Статистика самолечения"),
            BotCommand("logs", "Последние логи"),
            BotCommand("backup", "Создать бэкап"),
            BotCommand("rollback", "Откат кода"),
            BotCommand("health", "Проверка здоровья"),
            BotCommand("errors", "Последние ошибки"),
            BotCommand("balances", "Балансы сервисов"),
            BotCommand("goals_all", "Все цели (история)"),
            BotCommand("fix", "Самоисправление/интеграции"),
            BotCommand("skills", "Реестр навыков"),
            BotCommand("skills_pending", "Навыки ждут принятия"),
            BotCommand("skills_audit", "Аудит навыков (риск/покрытие)"),
            BotCommand("skills_fix", "Создать remediation-задачи навыков"),
            BotCommand("playbooks", "Топ playbooks"),
            BotCommand("workflow", "Статус workflow/state"),
            BotCommand("handoffs", "Трассировка handoff"),
            BotCommand("prefs", "Предпочтения владельца"),
            BotCommand("pubq", "Очередь публикаций"),
            BotCommand("pubrun", "Запустить очередь публикаций"),
            BotCommand("webop", "Web-operator сценарии"),
            BotCommand("clear_goals", "Очистить все цели"),
            BotCommand("nettest", "Проверка сети/интернета"),
            BotCommand("smoke", "Платформенный smoke-check"),
        ])

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
        # Explicit owner preference update (opt-in command)
        if self._try_set_preference_from_text(text):
            await self.send_message("Предпочтение сохранено. Могу учитывать в будущих задачах.")
            return

        lower = text.lower()
        # Approvals
        if self._pending_approvals:
            if lower in ("да", "yes", "ок", "ok", "approve", "✅", "👍"):
                # approve first pending
                request_id = next(iter(self._pending_approvals))
                future = self._pending_approvals.pop(request_id)
                if not future.done():
                    future.set_result(True)
                await self.send_message(f"Одобрено: {request_id}", level="approval")
                return
            if lower in ("нет", "no", "reject", "отмена", "❌", "👎"):
                request_id = next(iter(self._pending_approvals))
                future = self._pending_approvals.pop(request_id)
                if not future.done():
                    future.set_result(False)
                await self.send_message(f"Отклонено: {request_id}", level="approval")
                return

        # Simple shortcuts
        if any(kw in lower for kw in ["статус", "/status"]):
            if self._decision_loop and self._goal_engine:
                st = self._decision_loop.get_status()
                gs = self._goal_engine.get_stats()
                await self.send_message(
                    f"VITO Status\nDecision Loop: {'работает' if st['running'] else 'остановлен'}\n"
                    f"Тиков: {st['tick_count']}\nПотрачено сегодня: ${st['daily_spend']:.2f}\n"
                    f"Цели: {gs['total']} всего, {gs['completed']} выполнено, {gs['executing']} в работе, {gs['pending']} ожидают"
                )
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
                        response += "\n\nОтветь ✅ чтобы одобрить или ❌ чтобы отклонить."
                    await self.send_message(response, level="result")
                elif result.get("response"):
                    await self.send_message(result["response"], level="result")
                else:
                    await self.send_message("Понял. Чем могу помочь?")
                return
            except Exception as e:
                logger.warning(f"ConversationEngine error: {e}", extra={"event": "conversation_error"})

        await self.send_message("Не понял: это вопрос или задача? Напиши одним предложением, что нужно сделать.")

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

        # 1) Send binary/image files separately (no raw paths in text)
        bin_pattern = re.compile(r"(/(?:home/vito/vito-agent|tmp)/\S+\.(?:png|jpg|jpeg|webp|gif|pdf))")
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

        file_pattern = re.compile(r"(/home/vito/vito-agent/\S+\.(?:txt|md|json|py|csv|log))")
        found_files = file_pattern.findall(clean_text)

        # Replace file paths with inline content in message
        for fp in found_files:
            path = Path(fp)
            replacement = ""
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        rel_path = fp.replace("/home/vito/vito-agent/", "")
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

    async def _reject_stranger(self, update: Update) -> bool:
        """Отклоняет сообщения от не-владельцев."""
        if self._is_owner(update):
            return False
        chat_id = update.effective_chat.id if update.effective_chat else "unknown"
        logger.warning(
            f"Попытка доступа от чужого chat_id: {chat_id}",
            extra={"event": "unauthorized_access", "context": {"chat_id": chat_id}},
        )
        return True

    # ── Команды ──

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return
        await update.message.reply_text(
            "VITO на связи.\n\n"
            "/status — статус системы\n"
            "/goals — активные цели\n"
            "/spend — расходы за сегодня\n"
            "/approve — одобрить запрос\n"
            "/reject — отклонить запрос\n"
            "/goal <текст> — создать цель\n"
            "/prefs — предпочтения владельца",
            reply_markup=self._main_keyboard(),
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_stranger(update):
            return

        parts = ["VITO Status"]

        if self._decision_loop:
            st = self._decision_loop.get_status()
            parts.append(
                f"Decision Loop: {'работает' if st['running'] else 'остановлен'}\n"
                f"Тиков: {st['tick_count']}\n"
                f"Потрачено сегодня: ${st['daily_spend']:.2f}"
            )

        if self._goal_engine:
            gs = self._goal_engine.get_stats()
            parts.append(
                f"Цели: {gs['total']} всего, {gs['completed']} выполнено, "
                f"{gs['executing']} в работе, {gs['pending']} ожидают"
            )

        if self._pending_approvals:
            parts.append(f"Ожидают одобрения: {len(self._pending_approvals)}")

        await update.message.reply_text("\n\n".join(parts), reply_markup=self._main_keyboard())
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
        spend = self._llm_router.get_daily_spend() if self._llm_router else 0
        limit = settings.DAILY_LIMIT_USD
        await update.message.reply_text(
            f"Расходы сегодня: ${spend:.2f} / ${limit:.2f}\n"
            f"Осталось: ${max(limit - spend, 0):.2f}",
            reply_markup=self._main_keyboard(),
        )
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
        await update.message.reply_text(f"Одобрено: {request_id}", reply_markup=self._main_keyboard())
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
        await update.message.reply_text(f"Отклонено: {request_id}", reply_markup=self._main_keyboard())
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
        await update.message.reply_text(
            f"Цель создана: [{goal.goal_id}] {goal.title}\n"
            f"Приоритет: HIGH (от владельца)",
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

    async def _on_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Приём файлов/фото/видео от владельца и запуск document_agent."""
        if await self._reject_stranger(update):
            return
        if not update.message:
            return
        if not self._agent_registry:
            await update.message.reply_text("AgentRegistry не подключён.", reply_markup=self._main_keyboard())
            return

        attachment_dir = Path("/home/vito/vito-agent/input/attachments")
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
            out_dir = Path("/home/vito/vito-agent/output/attachments")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{Path(file_path).stem}_extracted.txt"
            out_path.write_text(extracted, encoding="utf-8", errors="ignore")

            preview = extracted[:3000]
            if len(extracted) > 3000:
                preview += f"\n\n(Полный текст сохранён в {out_path.relative_to(Path('/home/vito/vito-agent'))})"
            await update.message.reply_text(preview, reply_markup=self._main_keyboard())

            # Brainstorm from extracted text if applicable
            if await self._maybe_brainstorm_from_text(update, extracted):
                return

            # If conversation_engine exists, pass extracted text for natural language handling
            if self._conversation_engine:
                try:
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

        self._log_owner_request(text, source="text")

        lower = text.lower()
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

        if any(kw in lower for kw in [
            "очисти очередь",
            "очисти очередь целей",
            "удали все цели",
            "удали цели",
            "очисти цели",
            "сними все цели",
            "убери все цели",
            "delete all goals",
        ]):
            await self._cmd_clear_goals(update, context)
            return

        # Schedule from plain text (no command required)
        if await self._maybe_schedule_from_text(update, text):
            return

        # Brainstorm from plain text (no command required)
        if await self._maybe_brainstorm_from_text(update, text):
            return

        # 0. Accept secrets/key updates via Telegram (KEY=VALUE or "set KEY=VALUE")
        if self._try_set_env_from_text(text):
            await update.message.reply_text(
                "Ключ принят и сохранён. Если нужен перезапуск сервиса — скажи 'перезапусти'.",
                reply_markup=self._main_keyboard(),
            )
            return

        # 1. Обработка нажатий persistent-кнопок
        if text in self._button_map:
            cmd = self._button_map[text]
            handler = {
                "status": self._cmd_status,
                "goals": self._cmd_goals,
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
        if any(kw in lower for kw in ["баланс", "balance", "balances", "остатки", "сколько на счетах", "сколько осталось"]):
            await self._cmd_balances(update, context)
            return

        # 2. Pending approvals — да/нет/✅/❌
        if self._pending_approvals:
            if lower in ("да", "yes", "ок", "ok", "approve", "✅", "👍"):
                await self._cmd_approve(update, context)
                return
            elif lower in ("нет", "no", "reject", "отмена", "❌", "👎"):
                await self._cmd_reject(update, context)
                return

        # 2.5. Goal approval — approve goals in WAITING_APPROVAL status
        if lower in ("да", "yes", "ок", "ok", "approve", "✅", "👍") and self._goal_engine:
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
        elif lower in ("нет", "no", "reject", "отмена", "❌", "👎") and self._goal_engine:
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

        # 3. ConversationEngine — живой разговор
        if self._conversation_engine:
            try:
                result = await self._conversation_engine.process_message(text)

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
                        response += "\n\nОтветь ✅ чтобы одобрить или ❌ чтобы отклонить."
                    await update.message.reply_text(response, reply_markup=self._main_keyboard())
                elif result.get("response"):
                    await self._send_response(update, result["response"])
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
        await self._send_response(update, "\n\n".join(parts))
        logger.info("Команда /report выполнена", extra={"event": "cmd_report"})

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Остановить Decision Loop."""
        if await self._reject_stranger(update):
            return
        if self._decision_loop:
            self._decision_loop.stop()
            await update.message.reply_text("Decision Loop остановлен.", reply_markup=self._main_keyboard())
        else:
            await update.message.reply_text("Decision Loop не подключён.", reply_markup=self._main_keyboard())
        logger.info("Команда /stop выполнена", extra={"event": "cmd_stop"})

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Возобновить Decision Loop."""
        if await self._reject_stranger(update):
            return
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
        executing = self._goal_engine.get_all_goals(status=GoalStatus.EXECUTING)
        if not executing:
            await update.message.reply_text("Нет задач в работе.", reply_markup=self._main_keyboard())
            return
        lines = ["Задачи в работе:"]
        for g in executing[:10]:
            lines.append(f"  [{g.goal_id}] {g.title} (${g.estimated_cost_usd:.2f})")
        await update.message.reply_text("\n".join(lines), reply_markup=self._main_keyboard())
        logger.info("Команда /tasks выполнена", extra={"event": "cmd_tasks"})

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
                formatted = self._judge_protocol.format_verdict_for_telegram(verdict)
                await update.message.reply_text(formatted, reply_markup=self._main_keyboard())
            except Exception as e:
                await update.message.reply_text(f"Ошибка анализа: {e}", reply_markup=self._main_keyboard())
        logger.info(f"Команда /deep выполнена: {text[:50]}", extra={"event": "cmd_deep"})

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
        await query.edit_message_text(
            text=f"{query.message.text}\n\n— {label}",
        )

        logger.info(
            f"Inline {label.lower()}: {request_id}",
            extra={"event": f"inline_{'approved' if approved else 'rejected'}",
                   "context": {"request_id": request_id}},
        )

    # ── API для других модулей ──

    def _inline_file_paths(self, text: str) -> str:
        """Replace file paths in text with inline content.

        Short files (<500 chars): full content.
        Long files: first 500 chars + relative path reference.
        """
        import re

        file_pattern = re.compile(r"(/home/vito/vito-agent/\S+\.(?:txt|md|json|py|csv|log))")
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
                        rel_path = fp.replace("/home/vito/vito-agent/", "")
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
            clean = self._inline_file_paths(guarded)
            if len(clean) > 4000:
                clean = clean[:4000] + "..."
            await self._bot.send_message(chat_id=self._owner_id, text=clean)
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
            return True
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_approvals[request_id] = future

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
