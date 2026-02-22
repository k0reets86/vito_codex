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
import atexit
import os
import signal
import sys
from datetime import datetime, timezone

# ── Защита от дублирования процессов ──
PIDFILE = "/tmp/vito_agent.pid"


def _is_vito_running(pid: int) -> bool:
    """Check if PID is alive AND is a VITO main.py process."""
    try:
        cmdline_path = f"/proc/{pid}/cmdline"
        if not os.path.exists(cmdline_path):
            return False
        with open(cmdline_path, "rb") as f:
            cmdline = f.read().decode("utf-8", errors="replace")
        return "main.py" in cmdline and pid != os.getpid()
    except (OSError, PermissionError):
        return False


def _acquire_pidlock():
    """Check PID file. If another VITO is running — exit. Otherwise write our PID."""
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old_pid = int(f.read().strip())
            if _is_vito_running(old_pid):
                print(f"[VITO] Another instance PID {old_pid} is running. Exiting.")
                sys.exit(0)  # exit 0 so systemd doesn't rapid-restart
        except (ValueError, OSError):
            pass  # stale/corrupt pidfile

    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))


_acquire_pidlock()


def _cleanup_pidfile():
    try:
        os.unlink(PIDFILE)
    except OSError:
        pass


atexit.register(_cleanup_pidfile)

from comms_agent import CommsAgent
from config.logger import get_logger
from config.settings import settings
from decision_loop import DecisionLoop
from financial_controller import FinancialController
from goal_engine import GoalEngine
from llm_router import LLMRouter, TaskType
from memory.memory_manager import MemoryManager

from agents.agent_registry import AgentRegistry
from agents.vito_core import VITOCore
from agents.browser_agent import BrowserAgent
from agents.devops_agent import DevOpsAgent
from agents.research_agent import ResearchAgent
from agents.quality_judge import QualityJudge
from agents.trend_scout import TrendScout
from agents.content_creator import ContentCreator
from agents.ecommerce_agent import ECommerceAgent
from agents.seo_agent import SEOAgent
from agents.smm_agent import SMMAgent
from agents.marketing_agent import MarketingAgent
from agents.email_agent import EmailAgent
from agents.publisher_agent import PublisherAgent
from agents.translation_agent import TranslationAgent
from agents.analytics_agent import AnalyticsAgent
from agents.economics_agent import EconomicsAgent
from agents.security_agent import SecurityAgent
from agents.legal_agent import LegalAgent
from agents.risk_agent import RiskAgent
from agents.account_manager import AccountManager
from agents.partnership_agent import PartnershipAgent
from agents.hr_agent import HRAgent
from agents.document_agent import DocumentAgent

from platforms.gumroad import GumroadPlatform
from platforms.etsy import EtsyPlatform
from platforms.kofi import KofiPlatform
from platforms.wordpress import WordPressPlatform
from platforms.medium import MediumPlatform
from platforms.printful import PrintfulPlatform
from platforms.amazon_kdp import AmazonKDPPlatform
from platforms.youtube import YouTubePlatform
from platforms.substack import SubstackPlatform
from platforms.creative_fabrica import CreativeFabricaPlatform
from platforms.twitter import TwitterPlatform
from platforms.image_generator import ImageGenerator

from code_generator import CodeGenerator
from self_healer import SelfHealer
from self_updater import SelfUpdater
from knowledge_updater import KnowledgeUpdater
from conversation_engine import ConversationEngine
from judge_protocol import JudgeProtocol

VERSION = "0.3.0"

logger = get_logger("main", agent="vito_core")


class VITO:
    def __init__(self):
        self.running = False
        self.goal_engine = GoalEngine()
        self.llm_router = LLMRouter()
        self.memory = MemoryManager()
        self.finance = FinancialController()
        # Wire finance into LLM router for budget enforcement
        self.llm_router.set_finance(self.finance)
        self.comms = CommsAgent()

        # Agent Registry + 23 агентов
        self.registry = AgentRegistry()
        self._init_agents()

        # v0.3.0: Новые модули
        self.self_healer = SelfHealer(
            llm_router=self.llm_router, memory=self.memory, comms=self.comms
        )
        self.self_updater = SelfUpdater(
            memory=self.memory, comms=self.comms
        )
        self.code_generator = CodeGenerator(
            llm_router=self.llm_router, self_updater=self.self_updater, comms=self.comms
        )
        self.knowledge_updater = KnowledgeUpdater(
            llm_router=self.llm_router, memory=self.memory
        )
        self.conversation_engine = ConversationEngine(
            llm_router=self.llm_router, memory=self.memory, goal_engine=self.goal_engine,
            finance=self.finance, agent_registry=self.registry,
            self_healer=self.self_healer, self_updater=self.self_updater,
            knowledge_updater=self.knowledge_updater,
            code_generator=self.code_generator,
        )
        self.judge_protocol = JudgeProtocol(
            llm_router=self.llm_router, memory=self.memory, comms=self.comms
        )

        self.decision_loop = DecisionLoop(
            goal_engine=self.goal_engine,
            llm_router=self.llm_router,
            memory=self.memory,
            agent_registry=self.registry,
        )
        self.decision_loop.set_self_healer(self.self_healer)
        self.decision_loop._code_generator = self.code_generator
        # Smart routing: give decision_loop access to platforms
        self.decision_loop._platforms = self._platforms_commerce
        self.decision_loop._image_generator = self._image_generator
        self.decision_loop._comms = self.comms
        self.conversation_engine.decision_loop = self.decision_loop
        self.conversation_engine.judge_protocol = self.judge_protocol

        self.comms.set_modules(
            goal_engine=self.goal_engine,
            llm_router=self.llm_router,
            decision_loop=self.decision_loop,
            agent_registry=self.registry,
            self_healer=self.self_healer,
            self_updater=self.self_updater,
            conversation_engine=self.conversation_engine,
            judge_protocol=self.judge_protocol,
            finance=self.finance,
        )

    def _init_agents(self) -> None:
        """Создаёт и регистрирует все 23 агента."""
        deps = dict(llm_router=self.llm_router, memory=self.memory, finance=self.finance, comms=self.comms)

        # Platforms
        platforms_commerce = {
            "gumroad": GumroadPlatform(),
            "etsy": EtsyPlatform(),
            "kofi": KofiPlatform(),
            "printful": PrintfulPlatform(),
        }
        platforms_publish = {
            "wordpress": WordPressPlatform(),
            "medium": MediumPlatform(),
        }

        # Infrastructure
        browser = BrowserAgent(**deps)

        # Browser-based platforms (v0.3.0)
        platforms_commerce["amazon_kdp"] = AmazonKDPPlatform(browser_agent=browser)
        platforms_commerce["creative_fabrica"] = CreativeFabricaPlatform(browser_agent=browser)
        platforms_publish["substack"] = SubstackPlatform(browser_agent=browser)
        # YouTube — read-only (trend analysis)
        self._youtube = YouTubePlatform()
        # Twitter/X — real posting
        self._twitter = TwitterPlatform()
        # Image Generator — Replicate/BFL/WaveSpeed/DALL-E + Cloudinary
        self._image_generator = ImageGenerator()
        # Social media platforms for SMMAgent
        social_platforms = {"twitter": self._twitter}
        quality_judge = QualityJudge(**deps)

        # All agents
        agents = [
            VITOCore(registry=self.registry, **deps),                          # 00
            TrendScout(browser_agent=browser, **deps),                         # 01
            ContentCreator(quality_judge=quality_judge, **deps),               # 02
            SMMAgent(platforms=social_platforms, **deps),                       # 03
            MarketingAgent(**deps),                                            # 04
            ECommerceAgent(platforms=platforms_commerce, **deps),               # 05
            SEOAgent(**deps),                                                  # 06
            EmailAgent(**deps),                                                # 07
            TranslationAgent(**deps),                                          # 08
            AnalyticsAgent(**deps),                                            # 09
            EconomicsAgent(**deps),                                            # 16
            LegalAgent(**deps),                                                # 11
            RiskAgent(**deps),                                                 # 12
            SecurityAgent(**deps),                                             # 13
            DevOpsAgent(**deps),                                               # 14
            HRAgent(**deps),                                                   # 15
            PartnershipAgent(**deps),                                          # 17
            ResearchAgent(**deps),                                             # 18
            DocumentAgent(**deps),                                             # 19
            AccountManager(**deps),                                            # 20
            browser,                                                           # 21
            PublisherAgent(quality_judge=quality_judge, platforms=platforms_publish, **deps),  # 22
            quality_judge,                                                     # Quality Judge
        ]

        for agent in agents:
            self.registry.register(agent)

        # Store platforms for later injection into decision_loop
        self._platforms_commerce = platforms_commerce

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
        await self.registry.start_all()

        self.running = True
        agent_count = len(self.registry.get_all_statuses())
        logger.info(
            f"VITO v{VERSION} готов к работе ({agent_count} агентов)",
            extra={"event": "startup_complete", "context": {"agents": agent_count}},
        )

    def _verify_api_keys(self) -> None:
        """Проверяет наличие критичных и опциональных API-ключей."""
        missing_critical = []
        if not settings.ANTHROPIC_API_KEY:
            missing_critical.append("ANTHROPIC_API_KEY")
        if not settings.TELEGRAM_BOT_TOKEN:
            missing_critical.append("TELEGRAM_BOT_TOKEN")
        if not settings.TELEGRAM_OWNER_CHAT_ID:
            missing_critical.append("TELEGRAM_OWNER_CHAT_ID")

        if missing_critical:
            logger.warning(
                f"Отсутствуют критичные ключи: {', '.join(missing_critical)}",
                extra={"event": "missing_keys", "context": {"keys": missing_critical}},
            )
        else:
            logger.info("Все критичные API-ключи на месте", extra={"event": "keys_ok"})

        # Optional keys — log which are available
        optional_keys = {
            "GOOGLE_API_KEY": settings.GOOGLE_API_KEY,
            "OPENAI_API_KEY": settings.OPENAI_API_KEY,
            "PERPLEXITY_API_KEY": settings.PERPLEXITY_API_KEY,
            "GUMROAD_API_KEY": settings.GUMROAD_API_KEY,
            "ETSY_KEYSTRING": settings.ETSY_KEYSTRING,
            "KOFI_API_KEY": settings.KOFI_API_KEY,
        }
        available = [k for k, v in optional_keys.items() if v]
        missing_optional = [k for k, v in optional_keys.items() if not v]
        if available:
            logger.info(
                f"Доступны ключи: {', '.join(available)}",
                extra={"event": "optional_keys_available", "context": {"keys": available}},
            )
        if missing_optional:
            logger.debug(
                f"Не настроены: {', '.join(missing_optional)}",
                extra={"event": "optional_keys_missing", "context": {"keys": missing_optional}},
            )

    # ── Расписание периодических задач ──

    async def scheduler(self) -> None:
        """Планировщик задач по расписанию: 02:00-08:00 + проактивность каждые 4ч."""
        last_run: dict[str, str] = {}

        while self.running:
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            hour = now.hour

            if hour == 2 and last_run.get("security_audit") != today:
                last_run["security_audit"] = today
                await self._security_audit()

            if hour == 3 and last_run.get("consolidation") != today:
                last_run["consolidation"] = today
                await self._night_consolidation()

            if hour == 6 and last_run.get("trend_scout") != today:
                last_run["trend_scout"] = today
                await self._morning_scout()

            if hour == 8 and last_run.get("morning_report") != today:
                last_run["morning_report"] = today
                await self._morning_report()

            # v0.3.0: Проактивные проверки каждые 4 часа (10, 14, 18, 22)
            if hour in (10, 14, 18, 22):
                proactive_key = f"proactive_{hour}"
                if last_run.get(proactive_key) != today:
                    last_run[proactive_key] = today
                    await self._proactive_check()

            # Auto-stop idle agents every minute
            try:
                stopped = await self.registry.stop_idle_agents()
                if stopped:
                    logger.info(
                        f"Auto-stopped {stopped} idle agents",
                        extra={"event": "idle_cleanup", "context": {"stopped": stopped}},
                    )
            except Exception:
                pass

            await asyncio.sleep(60)

    async def _night_consolidation(self) -> None:
        """03:00 — анализ дня, сохранение навыков, обновление базы знаний."""
        logger.info("Ночная консолидация начата", extra={"event": "consolidation_start"})
        stats = self.goal_engine.get_stats()
        logger.info(
            f"Статистика дня: {stats}",
            extra={"event": "daily_stats", "context": stats},
        )

        # Cleanup resolved errors older than 7 days
        try:
            deleted = self.self_healer.cleanup_old_errors(days=7)
            if deleted:
                logger.info(
                    f"Очищено {deleted} старых ошибок",
                    extra={"event": "error_cleanup_done", "context": {"deleted": deleted}},
                )
        except Exception as e:
            logger.debug(f"Ошибка очистки: {e}", extra={"event": "cleanup_error"})

        logger.info("Ночная консолидация завершена", extra={"event": "consolidation_done"})

    async def _security_audit(self) -> None:
        """02:00 — ночной аудит безопасности."""
        logger.info("Ночной аудит безопасности", extra={"event": "security_audit_start"})
        try:
            result = await self.registry.dispatch("security")
            if result and result.success:
                logger.info(f"Аудит завершён: {result.output}", extra={"event": "security_audit_done"})
        except Exception as e:
            logger.warning(f"Ошибка аудита безопасности: {e}", extra={"event": "security_audit_error"})

    async def _morning_scout(self) -> None:
        """06:00 — trend_scout + knowledge_updater (по понедельникам) + weekly planning."""
        logger.info("Утренняя разведка начата", extra={"event": "scout_start"})
        try:
            result = await self.registry.dispatch("trend_scan")
            if result and result.success:
                logger.info("TrendScout завершил сканирование", extra={"event": "trend_scan_done"})
        except Exception as e:
            logger.warning(f"TrendScout ошибка: {e}", extra={"event": "trend_scan_error"})

        now = datetime.now(timezone.utc)
        if now.weekday() == 0:  # понедельник
            logger.info(
                "Понедельник — обновление знаний + недельное планирование",
                extra={"event": "monday_planning"},
            )
            try:
                results = await self.knowledge_updater.run_weekly_update()
                logger.info(
                    f"Knowledge update завершён: {results}",
                    extra={"event": "knowledge_update_done", "context": results},
                )
            except Exception as e:
                logger.warning(f"Knowledge update ошибка: {e}", extra={"event": "knowledge_update_error"})

            # Weekly planning — create calendar for the week
            await self._weekly_planning()

        logger.info("Утренняя разведка завершена", extra={"event": "scout_done"})

    async def _weekly_planning(self) -> None:
        """Понедельник: создание недельного контент-плана и расписания.

        Использует LLM 1 раз на всю неделю (экономия!) + результаты TrendScout.
        Сохраняет в SQLite weekly_calendar — Decision Loop читает оттуда.
        """
        import sqlite3
        from datetime import timedelta

        logger.info("Недельное планирование начато", extra={"event": "weekly_plan_start"})

        # 1. Init calendar table (no LLM)
        conn = sqlite3.connect(settings.SQLITE_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                day_of_week TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                task_type TEXT DEFAULT 'production',
                cost REAL DEFAULT 0.05,
                roi REAL DEFAULT 5.0,
                status TEXT DEFAULT 'pending',
                result TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        # 2. Get context from memory (no LLM)
        trends_context = ""
        try:
            trends = self.memory.search_knowledge("тренды ниши продукты", n_results=5)
            if trends:
                trends_context = "\n".join(f"- {t['text'][:150]}" for t in trends)
        except Exception:
            pass

        skills_context = ""
        try:
            skills = self.memory.get_top_skills(limit=5)
            if skills:
                skills_context = "\n".join(f"- {s['name']}: {s['description'][:100]}" for s in skills)
        except Exception:
            pass

        # 3. Generate weekly plan via LLM (1 call for whole week)
        now = datetime.now(timezone.utc)
        week_dates = [(now + timedelta(days=i)).strftime("%Y-%m-%d (%A)") for i in range(7)]

        prompt = (
            "Ты VITO — автономный AI-агент для заработка на цифровых продуктах.\n\n"
            "Создай конкретный план на неделю. Каждый день — ОДНА задача.\n"
            "Платформы: Gumroad (продукты), Printful (принты одежды), Twitter (контент), Etsy (листинги).\n\n"
            f"Тренды из разведки:\n{trends_context or '(нет данных)'}\n\n"
            f"Навыки:\n{skills_context or '(нет навыков)'}\n\n"
            "Даты:\n" + "\n".join(week_dates) + "\n\n"
            "ВАЖНО:\n"
            "- Понедельник: разведка трендов и планирование\n"
            "- Вторник-Четверг: создание продуктов и контента\n"
            "- Пятница: публикация и SEO\n"
            "- Суббота: аналитика и оптимизация\n"
            "- Воскресенье: продвижение в соцсетях\n\n"
            "Формат ответа — по строкам, каждая:\n"
            "ДАТА | ЗАГОЛОВОК | ОПИСАНИЕ (3-4 предложения с конкретными шагами)\n"
            "Без лишних слов, только 7 строк."
        )

        try:
            response = await self.llm_router.call_llm(
                task_type=TaskType.ROUTINE,
                prompt=prompt,
                estimated_tokens=1500,
            )
        except Exception as e:
            logger.warning(f"Weekly planning LLM error: {e}")
            response = None

        if not response:
            # Fallback: hardcoded week template (no LLM cost)
            self._create_default_weekly_calendar(conn, now)
            conn.close()
            return

        # 4. Parse LLM response and insert into calendar
        # Clear old entries for this week first
        week_start = now.strftime("%Y-%m-%d")
        week_end = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        conn.execute(
            "DELETE FROM weekly_calendar WHERE date >= ? AND date < ?",
            (week_start, week_end),
        )

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        lines = [l.strip() for l in response.strip().split("\n") if l.strip() and "|" in l]

        for i, line in enumerate(lines[:7]):
            parts = line.split("|")
            if len(parts) >= 3:
                date_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
                title = parts[1].strip()
                description = parts[2].strip()
                day_name = day_names[i] if i < len(day_names) else "Day"

                conn.execute(
                    "INSERT INTO weekly_calendar (date, day_of_week, title, description) VALUES (?, ?, ?, ?)",
                    (date_str, day_name, title, description),
                )

        conn.commit()
        conn.close()

        # 5. Notify owner
        plan_summary = "\n".join(lines[:7]) if lines else "(план не удалось распарсить)"
        await self.comms.send_message(
            f"VITO Недельный план:\n\n{plan_summary[:800]}"
        )
        logger.info(
            f"Недельный план создан: {len(lines)} задач",
            extra={"event": "weekly_plan_done", "context": {"tasks": len(lines)}},
        )

    def _create_default_weekly_calendar(self, conn, now) -> None:
        """Fallback weekly calendar without LLM."""
        from datetime import timedelta

        defaults = [
            ("Monday", "Разведка трендов и анализ рынка",
             "Просканировать Reddit, проанализировать конкурентов на Gumroad, найти новые ниши."),
            ("Tuesday", "Создание цифрового продукта",
             "На основе разведки создать ebook/шаблон/планировщик. Сохранить в output/."),
            ("Wednesday", "Создание принтов для Printful",
             "Исследовать мемы, создать 3 дизайна для футболок/кружек. Рассчитать себестоимость."),
            ("Thursday", "Контент и статьи",
             "Написать статью по теме продуктов. Подготовить 5 постов для Twitter."),
            ("Friday", "Публикация и SEO",
             "Опубликовать продукт на Gumroad. Оптимизировать описания. Опубликовать пост в Twitter."),
            ("Saturday", "Аналитика и оптимизация",
             "Проверить продажи, проанализировать расходы, оптимизировать SEO."),
            ("Sunday", "Продвижение и соцсети",
             "Продвижение продуктов в Twitter. Подготовка к следующей неделе."),
        ]

        for i, (day, title, desc) in enumerate(defaults):
            date_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT OR REPLACE INTO weekly_calendar (date, day_of_week, title, description) VALUES (?, ?, ?, ?)",
                (date_str, day, title, desc),
            )
        conn.commit()
        logger.info("Fallback weekly calendar created", extra={"event": "weekly_plan_fallback"})

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

    async def _proactive_check(self) -> None:
        """v0.3.0: Проактивная проверка каждые 4 часа — делится достижениями, предлагает шаги."""
        logger.info("Проактивная проверка", extra={"event": "proactive_check_start"})
        try:
            stats = self.goal_engine.get_stats()
            completed_today = stats.get("completed", 0)

            if completed_today > 0:
                await self.comms.send_message(
                    f"VITO Проактивный отчёт\n\n"
                    f"Выполнено целей: {completed_today}\n"
                    f"Потрачено: ${self.llm_router.get_daily_spend():.2f}\n"
                    f"Рекомендую: продолжать работу по текущим целям."
                )

            # Предложение следующих шагов если нет задач
            pending = stats.get("pending", 0)
            executing = stats.get("executing", 0)
            if pending == 0 and executing == 0:
                await self.comms.send_message(
                    "VITO: Нет активных задач. Предлагаю:\n"
                    "1. /trends — просканировать новые тренды\n"
                    "2. /deep <тема> — анализ перспективной ниши\n"
                    "3. /goal <задача> — создать новую цель"
                )

        except Exception as e:
            logger.warning(f"Проактивная проверка ошибка: {e}", extra={"event": "proactive_check_error"})

    # ── Shutdown ──

    async def shutdown(self) -> None:
        """Корректное завершение всех подсистем."""
        if not self.running:
            return
        self.running = False
        logger.info("VITO завершает работу...", extra={"event": "shutdown_start"})
        self.decision_loop.stop()
        await self.registry.stop_all()
        await self.comms.stop()
        self.finance.close()
        await self.memory.close()
        logger.info("VITO остановлен", extra={"event": "shutdown_complete"})


async def main() -> None:
    vito = VITO()

    loop = asyncio.get_running_loop()

    await vito.startup()

    tasks = [
        asyncio.create_task(vito.decision_loop.run(), name="decision_loop"),
        asyncio.create_task(vito.scheduler(), name="scheduler"),
    ]

    def handle_signal(sig: int) -> None:
        logger.info(
            f"Получен сигнал {signal.Signals(sig).name}",
            extra={"event": "signal_received", "context": {"signal": sig}},
        )
        for t in tasks:
            t.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

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
