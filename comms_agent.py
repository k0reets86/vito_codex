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
        self._agent_registry = None
        self._self_healer = None
        self._self_updater = None
        self._conversation_engine = None
        self._judge_protocol = None
        self._finance = None

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
        self._app.add_handler(CommandHandler("healer", self._cmd_healer))
        self._app.add_handler(CommandHandler("logs", self._cmd_logs))
        self._app.add_handler(CommandHandler("backup", self._cmd_backup))
        self._app.add_handler(CommandHandler("rollback", self._cmd_rollback))
        self._app.add_handler(CommandHandler("health", self._cmd_health))
        self._app.add_handler(CommandHandler("errors", self._cmd_errors))
        self._app.add_handler(CommandHandler("balances", self._cmd_balances))
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

    async def _send_response(self, update: Update, text: str) -> None:
        """Send response with smart file handling.

        Detects file paths in text → reads file content and sends inline.
        Short files (<500 chars): full content in chat.
        Long files: first 500 chars + "полный текст сохранён в <relative path>".
        NEVER sends raw file paths to owner.
        """
        import re

        file_pattern = re.compile(r"(/home/vito/vito-agent/\S+\.(?:txt|md|json|py|csv|log))")
        found_files = file_pattern.findall(text)

        # Replace file paths with inline content in message
        clean_text = text
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
        """Произвольное текстовое сообщение от владельца → ConversationEngine."""
        if await self._reject_stranger(update):
            return

        text = update.message.text.strip()
        if not text:
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
            f"Принял как задачу. Используй /goal для явного создания цели.\n"
            f'Твоё сообщение: "{text[:80]}..."',
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
        await update.message.reply_text("\n\n".join(parts), reply_markup=self._main_keyboard())
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
                f"(Opus → GPT-4o → Perplexity → Opus, ~$0.50)",
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
            checker = BalanceChecker()
            balances = await checker.check_all()

            # Add internal VITO spend data
            internal = {}
            if self._finance:
                internal["daily_spent"] = self._finance.get_daily_spent()
                internal["daily_earned"] = self._finance.get_daily_earned()
                internal["daily_limit"] = settings.DAILY_LIMIT_USD

            report = checker.format_report(balances, include_internal=internal)
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

    async def send_message(self, text: str) -> bool:
        """Отправляет сообщение владельцу. File paths auto-inlined."""
        if not self._bot:
            logger.warning("Бот не запущен — сообщение не отправлено", extra={"event": "send_no_bot"})
            return False
        try:
            clean = self._inline_file_paths(text)
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
