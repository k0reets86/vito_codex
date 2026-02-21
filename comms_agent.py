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

logger = get_logger("comms_agent", agent="comms_agent")


class CommsAgent:
    def __init__(self):
        self._bot: Optional[Bot] = None
        self._app: Optional[Application] = None
        self._owner_id: int = int(settings.TELEGRAM_OWNER_CHAT_ID)

        # Очередь запросов на одобрение: request_id → asyncio.Future
        self._pending_approvals: dict[str, asyncio.Future] = {}

        # Обратные ссылки на модули — устанавливаются через set_modules()
        self._goal_engine = None
        self._llm_router = None
        self._decision_loop = None

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
        self, goal_engine=None, llm_router=None, decision_loop=None, agent_registry=None
    ) -> None:
        """Привязывает модули после инициализации (избегаем циклических импортов)."""
        self._goal_engine = goal_engine
        self._llm_router = llm_router
        self._decision_loop = decision_loop
        self._agent_registry = agent_registry

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
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))

        await self._app.initialize()

        await self._bot.set_my_commands([
            BotCommand("status", "Статус системы"),
            BotCommand("goals", "Активные цели"),
            BotCommand("spend", "Расходы за сегодня"),
            BotCommand("approve", "Одобрить запрос"),
            BotCommand("reject", "Отклонить запрос"),
            BotCommand("goal", "Создать цель"),
            BotCommand("agents", "Список агентов"),
        ])

        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        logger.info("Telegram бот запущен", extra={"event": "bot_started"})
        await self.send_message("VITO запущен и готов к работе.")

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
            "/goal <текст> — создать цель",
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

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Произвольное текстовое сообщение от владельца → цель."""
        if await self._reject_stranger(update):
            return

        text = update.message.text.strip()
        if not text:
            return

        # Обработка нажатий persistent-кнопок
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
            # "Новая цель" — подсказка
            await update.message.reply_text(
                "Отправь текст цели, и я создам её.",
                reply_markup=self._main_keyboard(),
            )
            return

        # Если есть pending approval — считаем ответом на него
        if self._pending_approvals:
            lower = text.lower()
            if lower in ("да", "yes", "ок", "ok", "approve"):
                await self._cmd_approve(update, context)
                return
            elif lower in ("нет", "no", "reject", "отмена"):
                await self._cmd_reject(update, context)
                return

        # Иначе — создаём цель
        await update.message.reply_text(
            f"Принял как задачу. Используй /goal для явного создания цели.\n"
            f"Твоё сообщение: \"{text[:80]}...\"",
            reply_markup=self._main_keyboard(),
        )
        logger.info(
            f"Сообщение от владельца: {text[:100]}",
            extra={"event": "owner_message"},
        )

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

    async def send_message(self, text: str) -> bool:
        """Отправляет сообщение владельцу."""
        if not self._bot:
            logger.warning("Бот не запущен — сообщение не отправлено", extra={"event": "send_no_bot"})
            return False
        try:
            await self._bot.send_message(chat_id=self._owner_id, text=text)
            logger.info(
                f"Сообщение отправлено ({len(text)} символов)",
                extra={"event": "message_sent", "context": {"length": len(text)}},
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}", extra={"event": "send_failed"}, exc_info=True)
            return False

    async def send_file(self, file_path: str, caption: str = "") -> bool:
        """Отправляет файл владельцу (для превью продуктов)."""
        if not self._bot:
            return False
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Файл не найден: {file_path}", extra={"event": "file_not_found"})
            return False
        try:
            with open(path, "rb") as f:
                await self._bot.send_document(
                    chat_id=self._owner_id, document=f, caption=caption[:1024]
                )
            logger.info(
                f"Файл отправлен: {path.name}",
                extra={"event": "file_sent", "context": {"file": path.name}},
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}", extra={"event": "file_send_failed"}, exc_info=True)
            return False

    async def request_approval(
        self, request_id: str, message: str, timeout_seconds: int = 3600
    ) -> Optional[bool]:
        """Запрашивает одобрение у владельца. Возвращает True/False/None (timeout)."""
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_approvals[request_id] = future

        inline_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Одобрить", callback_data=f"approve:{request_id}"),
                InlineKeyboardButton("Отклонить", callback_data=f"reject:{request_id}"),
            ]
        ])
        if self._bot:
            await self._bot.send_message(
                chat_id=self._owner_id,
                text=message,
                reply_markup=inline_kb,
            )
        else:
            await self.send_message(message)

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

    async def send_morning_report(self, report: str) -> bool:
        """Отправляет утренний отчёт."""
        return await self.send_message(report)

    async def notify_error(self, module: str, error: str) -> bool:
        """Уведомляет владельца о критической ошибке."""
        return await self.send_message(
            f"VITO Error | {module}\n{error}"
        )
