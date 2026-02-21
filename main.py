"""VITO — Autonomous AI Agent.

Точка входа. Инициализация компонентов, запуск Decision Loop,
расписание периодических задач, graceful shutdown.

Расписание (из документации):
  03:00 — ночная консолидация памяти
  06:00 — trend_scout + knowledge_updater (по понедельникам)
  08:00 — утренний отчёт владельцу в Telegram
  Каждые 5 мин — Decision Loop (сердце системы)
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone

from comms_agent import CommsAgent
from config.logger import get_logger
from config.settings import settings
from decision_loop import DecisionLoop
from financial_controller import FinancialController
from goal_engine import GoalEngine
from llm_router import LLMRouter
from memory.memory_manager import MemoryManager

VERSION = "0.1.0"

logger = get_logger("main", agent="vito_core")


class VITO:
    def __init__(self):
        self.running = False
        self.goal_engine = GoalEngine()
        self.llm_router = LLMRouter()
        self.memory = MemoryManager()
        self.finance = FinancialController()
        self.comms = CommsAgent()
        self.decision_loop = DecisionLoop(
            goal_engine=self.goal_engine,
            llm_router=self.llm_router,
            memory=self.memory,
        )
        self.comms.set_modules(
            goal_engine=self.goal_engine,
            llm_router=self.llm_router,
            decision_loop=self.decision_loop,
        )

    async def startup(self) -> None:
        """Инициализация всех подсистем."""
        logger.info(
            f"VITO v{VERSION} запускается",
            extra={
                "event": "startup",
                "context": {
                    "version": VERSION,
                    "daily_limit": settings.DAILY_LIMIT_USD,
                    "chroma_path": settings.CHROMA_PATH,
                    "sqlite_path": settings.SQLITE_PATH,
                },
            },
        )

        self._verify_api_keys()

        # SQLite и ChromaDB подключаются лениво при первом обращении.
        # PostgreSQL пробуем подключить сразу — если недоступен, работаем без него.
        try:
            pg_pool = await self.memory._get_pg()
            self.finance.set_pg_pool(pg_pool)
            logger.info("PostgreSQL подключён", extra={"event": "pg_ready"})
        except Exception as e:
            logger.warning(
                f"PostgreSQL недоступен, работаем без долгосрочной памяти: {e}",
                extra={"event": "pg_unavailable"},
            )

        await self.comms.start()

        self.running = True
        logger.info(
            f"VITO v{VERSION} готов к работе",
            extra={"event": "startup_complete"},
        )

    def _verify_api_keys(self) -> None:
        """Проверяет наличие критичных API-ключей."""
        missing = []
        if not settings.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        if not settings.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not settings.TELEGRAM_OWNER_CHAT_ID:
            missing.append("TELEGRAM_OWNER_CHAT_ID")

        if missing:
            logger.warning(
                f"Отсутствуют ключи: {', '.join(missing)}",
                extra={"event": "missing_keys", "context": {"keys": missing}},
            )
        else:
            logger.info("Все критичные API-ключи на месте", extra={"event": "keys_ok"})

    # ── Расписание периодических задач ──

    async def scheduler(self) -> None:
        """Планировщик задач по расписанию: 03:00, 06:00, 08:00."""
        last_run: dict[str, str] = {}

        while self.running:
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            hour = now.hour

            if hour == 3 and last_run.get("consolidation") != today:
                last_run["consolidation"] = today
                await self._night_consolidation()

            if hour == 6 and last_run.get("trend_scout") != today:
                last_run["trend_scout"] = today
                await self._morning_scout()

            if hour == 8 and last_run.get("morning_report") != today:
                last_run["morning_report"] = today
                await self._morning_report()

            await asyncio.sleep(60)

    async def _night_consolidation(self) -> None:
        """03:00 — анализ дня, сохранение навыков, обновление базы знаний."""
        logger.info("Ночная консолидация начата", extra={"event": "consolidation_start"})
        stats = self.goal_engine.get_stats()
        logger.info(
            f"Статистика дня: {stats}",
            extra={"event": "daily_stats", "context": stats},
        )
        # TODO: анализ дня через LLM, уплотнение старых воспоминаний
        logger.info("Ночная консолидация завершена", extra={"event": "consolidation_done"})

    async def _morning_scout(self) -> None:
        """06:00 — trend_scout + knowledge_updater (по понедельникам)."""
        logger.info("Утренняя разведка начата", extra={"event": "scout_start"})
        now = datetime.now(timezone.utc)
        if now.weekday() == 0:  # понедельник
            logger.info(
                "Понедельник — запуск обновления базы знаний LLM",
                extra={"event": "knowledge_update_trigger"},
            )
            # TODO: knowledge_updater.py
        # TODO: trend_scout.py
        logger.info("Утренняя разведка завершена", extra={"event": "scout_done"})

    async def _morning_report(self) -> None:
        """08:00 — утренний отчёт владельцу в Telegram."""
        stats = self.goal_engine.get_stats()
        finance_block = self.finance.format_morning_finance()

        report = (
            f"VITO Отчёт | {datetime.now(timezone.utc).strftime('%d.%m.%Y')}\n\n"
            f"{finance_block}\n\n"
            f"Цели: выполнено {stats['completed']}, в работе {stats['executing']}, "
            f"ожидают {stats['pending']}\n"
            f"Успешность: {stats['success_rate']:.0%}"
        )

        logger.info(
            f"Утренний отчёт сформирован",
            extra={"event": "morning_report", "context": {"report": report}},
        )
        await self.comms.send_morning_report(report)

    # ── Shutdown ──

    async def shutdown(self) -> None:
        """Корректное завершение всех подсистем."""
        logger.info("VITO завершает работу...", extra={"event": "shutdown_start"})
        self.running = False
        self.decision_loop.stop()
        await self.comms.stop()
        self.finance.close()
        await self.memory.close()
        logger.info("VITO остановлен", extra={"event": "shutdown_complete"})


async def main() -> None:
    vito = VITO()

    loop = asyncio.get_running_loop()

    def handle_signal(sig: int) -> None:
        logger.info(
            f"Получен сигнал {signal.Signals(sig).name}",
            extra={"event": "signal_received", "context": {"signal": sig}},
        )
        asyncio.ensure_future(vito.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    await vito.startup()

    tasks = [
        asyncio.create_task(vito.decision_loop.run(), name="decision_loop"),
        asyncio.create_task(vito.scheduler(), name="scheduler"),
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await vito.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
