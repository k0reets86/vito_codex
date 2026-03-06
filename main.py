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
import time
from pathlib import Path
from datetime import datetime, timezone
from config.paths import PROJECT_ROOT

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
    if os.getenv("VITO_ALLOW_MULTI") == "1":
        return
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

# Bootstrap global DISPLAY for headed browser flows on headless server.
try:
    if os.getenv("VITO_BOOTSTRAP_XVFB", "1").lower() in {"1", "true", "yes", "on"}:
        from modules.display_bootstrap import ensure_display
        ensure_display()
except Exception:
    pass


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
from modules.owner_preference_model import OwnerPreferenceModel

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
from platforms.threads import ThreadsPlatform
from platforms.youtube import YouTubePlatform
from platforms.reddit import RedditPlatform
from platforms.tiktok import TikTokPlatform
from platforms.pinterest import PinterestPlatform
from platforms.image_generator import ImageGenerator

from code_generator import CodeGenerator
from self_healer import SelfHealer
from self_updater import SelfUpdater
from modules.skill_registry import SkillRegistry
from modules.time_sync import TimeSync
from modules.schedule_manager import ScheduleManager
from modules.platform_registry import PlatformRegistry
from modules.platform_smoke import PlatformSmoke
from modules.playbook_registry import PlaybookRegistry
from modules.publisher_queue import PublisherQueue
from modules.conversation_memory import ConversationMemory
from modules.cancel_state import CancelState
from modules.owner_task_state import OwnerTaskState
from modules.revenue_engine import RevenueEngine
from dashboard_server import DashboardServer
from knowledge_updater import KnowledgeUpdater
from conversation_engine import ConversationEngine
from judge_protocol import JudgeProtocol

VERSION = "0.3.0"

logger = get_logger("main", agent="vito_core")


class VITO:
    def __init__(self):
        self.running = False
        self._last_process_guard_ts = 0.0
        self.goal_engine = GoalEngine()
        self.llm_router = LLMRouter()
        self.memory = MemoryManager()
        self.conversation_memory = ConversationMemory(path=settings.CONVERSATION_HISTORY_PATH)
        self.cancel_state = CancelState(path=settings.CANCEL_STATE_PATH)
        self.owner_task_state = OwnerTaskState(path=settings.OWNER_TASK_STATE_PATH)
        self.revenue_engine = RevenueEngine()
        self.finance = FinancialController()
        self.comms = CommsAgent()
        try:
            self.memory.sync_skill_registry()
        except Exception:
            pass
        # Wire finance into LLM router for budget enforcement
        self.llm_router.set_finance(self.finance)
        # Wire comms into LLM router for approval dialogs
        self.llm_router.set_comms(self.comms)

        # Skill registry should exist before agents init
        self.skill_registry = SkillRegistry()
        try:
            self.skill_registry.audit_coverage()
        except Exception:
            pass
        try:
            self.skill_registry.register_from_capability_packs()
        except Exception:
            pass
        self.schedule_manager = ScheduleManager()
        self.platform_registry = PlatformRegistry()
        try:
            self.platform_registry.refresh()
        except Exception:
            pass
        self.platform_smoke = None
        try:
            # Bootstrap playbooks from historical facts once (if table is empty).
            PlaybookRegistry().ensure_bootstrap(limit=2000)
        except Exception:
            pass

        # Agent Registry + 23 агентов
        self.registry = AgentRegistry()
        self._init_agents()

        # v0.3.0: Новые модули
        self.self_updater = SelfUpdater(
            memory=self.memory, comms=self.comms
        )
        self.self_healer = SelfHealer(
            llm_router=self.llm_router, memory=self.memory, comms=self.comms, self_updater=self.self_updater
        )
        self.code_generator = CodeGenerator(
            llm_router=self.llm_router, self_updater=self.self_updater, comms=self.comms
        )
        # Wire code_generator/self_updater into VITOCore
        try:
            core = self.registry.get("vito_core")
            if core:
                core.code_generator = self.code_generator
                core.self_updater = self.self_updater
        except Exception:
            pass
        self.knowledge_updater = KnowledgeUpdater(
            llm_router=self.llm_router, memory=self.memory
        )
        # Load static commerce calendar into memory on startup
        try:
            self.knowledge_updater.load_static_calendar()
        except Exception:
            pass
        self.conversation_engine = ConversationEngine(
            llm_router=self.llm_router, memory=self.memory, goal_engine=self.goal_engine,
            finance=self.finance, agent_registry=self.registry,
            self_healer=self.self_healer, self_updater=self.self_updater,
            knowledge_updater=self.knowledge_updater,
            code_generator=self.code_generator, comms=self.comms,
            conversation_memory=self.conversation_memory,
            cancel_state=self.cancel_state,
            owner_task_state=self.owner_task_state,
        )
        self.judge_protocol = JudgeProtocol(
            llm_router=self.llm_router, memory=self.memory, comms=self.comms
        )
        self.time_sync = TimeSync(comms=self.comms)
        try:
            self.dashboard = DashboardServer(
                goal_engine=self.goal_engine,
                decision_loop=None,
                finance=self.finance,
                registry=self.registry,
                schedule_manager=self.schedule_manager,
                platform_registry=self.platform_registry,
                llm_router=self.llm_router,
                comms=self.comms,
            )
        except Exception:
            self.dashboard = None

        self.decision_loop = DecisionLoop(
            goal_engine=self.goal_engine,
            llm_router=self.llm_router,
            memory=self.memory,
            agent_registry=self.registry,
        )
        self.decision_loop.set_cancel_state(self.cancel_state)
        self.decision_loop.set_self_healer(self.self_healer)
        self.decision_loop._code_generator = self.code_generator
        # Smart routing: give decision_loop access to platforms
        self.decision_loop._platforms = self._platforms_commerce
        self.decision_loop._image_generator = self._image_generator
        self.decision_loop._comms = self.comms
        self.decision_loop._skill_registry = self.skill_registry
        try:
            if self.dashboard:
                self.dashboard.decision_loop = self.decision_loop
                self.dashboard.start()
        except Exception:
            pass
        self.conversation_engine.decision_loop = self.decision_loop
        self.conversation_engine.judge_protocol = self.judge_protocol
        try:
            self.publisher_queue = PublisherQueue(getattr(self, "_platforms_queue", self._platforms_commerce))
        except Exception:
            self.publisher_queue = None
        try:
            if self.dashboard:
                self.dashboard.publisher_queue = self.publisher_queue
        except Exception:
            pass

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
            skill_registry=self.skill_registry,
            weekly_planner=self._weekly_planning,
            schedule_manager=self.schedule_manager,
            publisher_queue=self.publisher_queue,
            cancel_state=self.cancel_state,
            owner_task_state=self.owner_task_state,
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
        social_platforms = {
            "twitter": self._twitter,
            "reddit": RedditPlatform(),
            "pinterest": PinterestPlatform(),
            "threads": ThreadsPlatform(),
        }
        quality_judge = QualityJudge(**deps)

        # All agents
        agents = [
            VITOCore(registry=self.registry, skill_registry=self.skill_registry, **deps),  # 00
            TrendScout(browser_agent=browser, **deps),                         # 01
            ContentCreator(quality_judge=quality_judge, **deps),               # 02
            SMMAgent(platforms=social_platforms, **deps),                       # 03
            MarketingAgent(**deps),                                            # 04
            ECommerceAgent(platforms=platforms_commerce, registry=self.registry, **deps),  # 05
            SEOAgent(**deps),                                                  # 06
            EmailAgent(**deps),                                                # 07
            TranslationAgent(**deps),                                          # 08
            AnalyticsAgent(registry=self.registry, **deps),                    # 09
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

        # Wire registry into agents that need it
        for agent in agents:
            if isinstance(agent, HRAgent):
                agent.registry = self.registry

        # Store platforms for later injection into decision_loop
        self._platforms_commerce = platforms_commerce
        self._platforms_social = {
            "twitter": TwitterPlatform(),
            "threads": ThreadsPlatform(),
            "youtube": YouTubePlatform(),
            "reddit": RedditPlatform(),
            "tiktok": TikTokPlatform(),
            "pinterest": PinterestPlatform(),
            "wordpress": platforms_publish.get("wordpress"),
            "medium": platforms_publish.get("medium"),
        }
        self._platforms_queue = {**self._platforms_commerce, **self._platforms_social}
        try:
            self.platform_smoke = PlatformSmoke(self._platforms_commerce)
        except Exception:
            self.platform_smoke = None

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
        # Time sync on startup
        try:
            await self.time_sync.check(reason="startup")
        except Exception:
            pass
        # Network check on startup (inside VITO process)
        try:
            from modules.network_utils import basic_net_report
            net = basic_net_report()
            logger.info(
                f"Network check: {net}",
                extra={"event": "network_check", "context": net},
            )
        except Exception:
            pass

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
            self._single_instance_watchdog()
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

            # Daily time sync at 01:00
            if hour == 1 and last_run.get("time_sync_daily") != today:
                last_run["time_sync_daily"] = today
                try:
                    await self.time_sync.check(reason="daily")
                except Exception:
                    pass

            # Weekly time sync on Monday at 04:00
            if hour == 4 and now.strftime("%A") == "Monday" and last_run.get("time_sync_weekly") != today:
                last_run["time_sync_weekly"] = today
                try:
                    await self.time_sync.check(reason="weekly")
                except Exception:
                    pass

            # Balance check at 12:00 — alerts only for low balances
            if hour == 12 and last_run.get("balance_check") != today:
                last_run["balance_check"] = today
                await self._scheduled_balance_check()

            # Daily platform smoke check at 13:00 (safe read-only checks)
            if hour == 13 and last_run.get("platform_smoke_daily") != today:
                last_run["platform_smoke_daily"] = today
                try:
                    await self._platform_smoke_check()
                except Exception:
                    pass

            # Daily commerce readiness loop at 14:00 (dry-run publish queue, evidence refresh)
            if hour == 14 and last_run.get("commerce_readiness_daily") != today:
                last_run["commerce_readiness_daily"] = today
                try:
                    await self._commerce_readiness_loop()
                except Exception:
                    pass

            # Wave D: Daily revenue cycle (Gumroad-first, approval-gated)
            revenue_hour = int(getattr(settings, "REVENUE_ENGINE_DAILY_HOUR_UTC", 15) or 15) % 24
            if (
                getattr(settings, "REVENUE_ENGINE_ENABLED", False)
                and hour == revenue_hour
                and last_run.get("revenue_cycle_daily") != today
            ):
                last_run["revenue_cycle_daily"] = today
                try:
                    await self._revenue_cycle_daily()
                except Exception:
                    pass

            # v0.3.0: Проактивные проверки каждые 4 часа (10, 14, 18, 22)
            if hour in (10, 14, 18, 22):
                proactive_key = f"proactive_{hour}"
                if last_run.get(proactive_key) != today:
                    last_run[proactive_key] = today
                    await self._proactive_check()

            # Weekly HR knowledge audit (Monday 05:00)
            if hour == 5 and now.strftime("%A") == "Monday" and last_run.get("hr_audit") != today:
                last_run["hr_audit"] = today
                try:
                    if self.registry:
                        await self.registry.dispatch("knowledge_audit")
                        await self.registry.dispatch("agent_development")
                except Exception:
                    pass

            # Daily skill registry audit (quality/risk/tests_coverage)
            if hour == 2 and last_run.get("skill_audit_daily") != today:
                last_run["skill_audit_daily"] = today
                try:
                    audited = self.skill_registry.audit_coverage()
                    rem = self.skill_registry.remediate_high_risk(limit=50)
                    logger.info(
                        "Daily skill audit completed",
                        extra={
                            "event": "skill_audit_daily_done",
                            "context": {
                                "audited": audited,
                                "remediation_created": rem.get("created", 0),
                                "remediation_open": rem.get("open_total", 0),
                            },
                        },
                    )
                except Exception:
                    pass

            # Daily static knowledge refresh (platform/model docs to memory)
            if hour == 7 and last_run.get("knowledge_refresh_daily") != today:
                last_run["knowledge_refresh_daily"] = today
                try:
                    self.knowledge_updater.run_daily_refresh()
                except Exception:
                    pass

            # Platform registry refresh every 6 hours
            if hour in (0, 6, 12, 18):
                pkey = f"platform_refresh_{hour}"
                if last_run.get(pkey) != today:
                    last_run[pkey] = today
                    try:
                        self.platform_registry.refresh()
                    except Exception:
                        pass

            # Network watchdog for Telegram DNS every hour (quiet unless broken)
            nkey = f"net_watchdog_{hour}"
            if last_run.get(nkey) != today:
                last_run[nkey] = today
                try:
                    await self._network_watchdog()
                except Exception:
                    pass

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

            # Run due scheduled tasks (calendar / reminders / reports)
            try:
                due = self.schedule_manager.acquire_due_tasks(
                    owner=f"main:{os.getpid()}",
                    limit=20,
                    lock_minutes=15,
                )
                for task in due:
                    await self._run_scheduled_task(task)
                    self.schedule_manager.mark_run(task)
            except Exception:
                pass

            await asyncio.sleep(60)

    def _single_instance_watchdog(self) -> None:
        """Quietly self-terminate duplicate runtime instance."""
        if os.getenv("VITO_ALLOW_MULTI") == "1":
            return
        if not getattr(settings, "PROCESS_GUARD_ENABLED", True):
            return
        interval = max(15, int(getattr(settings, "PROCESS_GUARD_INTERVAL_SEC", 90) or 90))
        now_mono = time.monotonic()
        if (now_mono - float(self._last_process_guard_ts or 0.0)) < interval:
            return
        self._last_process_guard_ts = now_mono
        try:
            from modules.process_guard import list_vito_main_pids, read_pidfile, select_primary_pid, write_pidfile

            me = int(os.getpid())
            pids = list_vito_main_pids()
            if me not in pids:
                pids.append(me)
            pidfile_pid = read_pidfile(PIDFILE)
            primary = select_primary_pid(pids, pidfile_pid=pidfile_pid)
            if not primary:
                write_pidfile(PIDFILE, me)
                return
            if primary == me:
                if pidfile_pid != me:
                    write_pidfile(PIDFILE, me)
                return

            logger.warning(
                f"Duplicate main.py detected; self-exit (self={me}, primary={primary}, pids={pids})",
                extra={"event": "process_guard_duplicate_exit", "context": {"self_pid": me, "primary_pid": primary, "pids": pids}},
            )
            self.running = False
            try:
                self.decision_loop.stop()
            except Exception:
                pass
            os._exit(0)
        except Exception:
            return

    async def _network_watchdog(self) -> None:
        """Check Telegram DNS reachability and notify via fallback channel if broken."""
        if not self._cron_notifications_enabled():
            logger.debug("Network watchdog notification skipped (cron notifications disabled)", extra={"event": "net_watchdog_skipped"})
            return
        from modules.network_utils import basic_net_report
        report = basic_net_report(["api.telegram.org", "gumroad.com", "google.com"])
        if report.get("ok"):
            return
        msg = (
            "⚠️ Network watchdog: DNS issue detected.\n"
            f"seccomp={report.get('seccomp')}\n"
            f"dns={report.get('dns')}"
        )
        try:
            await self.comms.send_message(msg, level="critical")
        except Exception:
            pass

    async def _platform_smoke_check(self) -> None:
        """Daily safe platform smoke checks and summary."""
        if not self.platform_smoke:
            return
        if not self._cron_notifications_enabled():
            logger.debug("Platform smoke summary skipped (cron notifications disabled)", extra={"event": "platform_smoke_skipped"})
            return
        results = await self.platform_smoke.run(names=["gumroad", "etsy", "kofi", "printful"])
        ok = sum(1 for r in results if r.get("status") == "success")
        fail = len(results) - ok
        logger.info(
            f"Platform smoke: ok={ok} fail={fail}",
            extra={"event": "platform_smoke_done", "context": {"results": results}},
        )
        try:
            await self.comms.send_message(
                f"Platform smoke done: ok={ok}, fail={fail}",
                level="cron",
            )
        except Exception:
            pass

    async def _commerce_readiness_loop(self) -> None:
        """Queue dry-run jobs on key platforms and process them for evidence/KPI freshness."""
        if not self.publisher_queue:
            return
        payloads = {
            "gumroad": {"dry_run": True, "name": "VITO daily readiness check", "price": 5},
            "etsy": {"dry_run": True, "title": "VITO readiness Etsy", "price": 5},
            "kofi": {"dry_run": True, "title": "VITO readiness Ko-fi", "price": 5},
            "printful": {"dry_run": True, "sync_product": {"name": "VITO readiness Printful"}},
            "twitter": {"dry_run": True, "text": "VITO readiness check"},
            "wordpress": {"dry_run": True, "title": "VITO readiness WP", "content": "<p>ok</p>", "status": "draft"},
            "threads": {"dry_run": True, "text": "VITO readiness check"},
            "reddit": {"dry_run": True, "title": "VITO readiness", "subreddit": "test", "text": "dry run"},
            "youtube": {"dry_run": True, "title": "VITO readiness", "description": "dry run"},
            "tiktok": {"dry_run": True, "title": "VITO readiness", "description": "dry run"},
        }
        enqueued = 0
        for platform, payload in payloads.items():
            if platform not in getattr(self, "_platforms_queue", {}):
                continue
            self.publisher_queue.enqueue(platform, payload, max_attempts=1, trace_id="daily_readiness")
            enqueued += 1
        results = await self.publisher_queue.process_all(limit=30)
        done = sum(1 for r in results if r.get("status") == "done")
        fail = sum(1 for r in results if r.get("status") == "failed")
        logger.info(
            "Commerce readiness loop done",
            extra={
                "event": "commerce_readiness_done",
                "context": {"enqueued": enqueued, "processed": len(results), "done": done, "failed": fail},
            },
        )

    async def _revenue_cycle_daily(self) -> None:
        """Wave D daily closed-loop cycle in safe mode (Gumroad-first)."""
        out = await self.revenue_engine.run_gumroad_cycle(
            registry=self.registry,
            llm_router=self.llm_router,
            comms=self.comms,
            publisher_queue=self.publisher_queue,
            topic="",
            dry_run=bool(getattr(settings, "REVENUE_ENGINE_DRY_RUN", True)),
            require_approval=bool(getattr(settings, "REVENUE_ENGINE_REQUIRE_APPROVAL", True)),
        )
        logger.info(
            f"Revenue cycle done: ok={out.get('ok')} cycle_id={out.get('cycle_id')} status={out.get('status', out.get('error', ''))}",
            extra={"event": "revenue_cycle_daily", "context": out},
        )
        if not self._cron_notifications_enabled():
            return
        try:
            msg = (
                "Revenue cycle daily:\n"
                f"- ok: {1 if out.get('ok') else 0}\n"
                f"- cycle_id: {out.get('cycle_id')}\n"
                f"- status: {out.get('status', out.get('error', 'unknown'))}\n"
                f"- topic: {out.get('topic', '')[:120]}"
            )
            await self.comms.send_message(msg, level="cron")
        except Exception:
            pass

    async def _night_consolidation(self) -> None:
        """03:00 — анализ дня, сохранение навыков, обновление базы знаний.

        Steps:
        1. Collect day stats (goals completed/failed, revenue, spend)
        2. Store daily summary to knowledge base
        3. Analyze errors → update patterns
        4. Update skill base (successful strategies)
        5. Cleanup old resolved errors
        """
        logger.info("Ночная консолидация начата", extra={"event": "consolidation_start"})

        # 1. Collect day statistics
        goal_stats = self.goal_engine.get_stats()
        pnl = self.finance.get_pnl(days=1)
        daily_spent = self.finance.get_daily_spent()
        daily_earned = self.finance.get_daily_earned()
        llm_spend = self.llm_router.get_daily_spend()

        logger.info(
            f"Статистика дня: goals={goal_stats}, P&L={pnl}",
            extra={"event": "daily_stats", "context": {**goal_stats, **pnl}},
        )

        # 2. Store daily summary to knowledge base
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = (
            f"Daily summary {today}: "
            f"Goals: {goal_stats['completed']} completed, {goal_stats['failed']} failed, "
            f"{goal_stats['pending']} pending. "
            f"Finance: spent ${daily_spent:.2f} (LLM: ${llm_spend:.2f}), "
            f"earned ${daily_earned:.2f}, net ${pnl['net_profit']:.2f}. "
            f"Success rate: {goal_stats['success_rate']:.0%}."
        )
        try:
            self.memory.store_knowledge(
                doc_id=f"daily_summary_{today}",
                text=summary,
                metadata={"type": "daily_summary", "date": today, **goal_stats, **pnl},
            )
        except Exception as e:
            logger.debug(f"Ошибка сохранения саммари: {e}", extra={"event": "summary_save_error"})

        # 2.1 Store owner preference snapshot
        try:
            prefs = OwnerPreferenceModel().list_preferences(limit=50)
            if prefs:
                snapshot = "; ".join(f"{p.get('pref_key')}: {p.get('value')}" for p in prefs)
                self.memory.store_knowledge(
                    doc_id=f"owner_prefs_snapshot_{today}",
                    text=f"Owner preferences snapshot {today}: {snapshot}",
                    metadata={"type": "owner_prefs_snapshot", "date": today},
                )
        except Exception:
            pass
        # 2.2 Write owner preference report
        try:
            from modules.owner_pref_metrics import OwnerPreferenceMetrics
            prefs = OwnerPreferenceModel().list_preferences(limit=200)
            metrics = OwnerPreferenceMetrics().summary()
            lines = [f"# Owner Preferences Report ({today})", "", "## Metrics"]
            for k, v in metrics.items():
                lines.append(f"- {k}: {v}")
            lines.append("")
            lines.append("## Preferences")
            if not prefs:
                lines.append("- None")
            else:
                for p in prefs:
                    lines.append(
                        f"- {p.get('pref_key')}: {p.get('value')} (conf={float(p.get('confidence',0)):.2f}, status={p.get('status')})"
                    )
            report_path = PROJECT_ROOT / "reports" / f"OWNER_PREFS_{today}.md"
            report_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass

        # 3. Analyze errors → update patterns
        try:
            error_stats = self.self_healer.get_error_stats()
            if error_stats.get("unresolved", 0) > 0:
                self.memory.save_pattern(
                    category="errors",
                    key=f"unresolved_{today}",
                    value=f"{error_stats['unresolved']} unresolved errors, "
                          f"resolution rate: {error_stats['resolution_rate']:.0%}",
                    confidence=0.8,
                )
            if error_stats.get("by_module"):
                top_module = error_stats["by_module"][0]
                self.memory.save_pattern(
                    category="error_hotspot",
                    key=f"hotspot_{today}",
                    value=f"Most errors from: {top_module['module']} ({top_module['cnt']} errors)",
                    confidence=0.7,
                )
        except Exception as e:
            logger.debug(f"Ошибка анализа ошибок: {e}", extra={"event": "error_analysis_error"})

        # 4. Save successful strategies as skills
        try:
            if goal_stats["completed"] > 0 and goal_stats["success_rate"] > 0.5:
                self.memory.save_skill(
                    name=f"daily_execution_{today}",
                    description=f"Day {today}: {goal_stats['completed']} goals completed with "
                                f"{goal_stats['success_rate']:.0%} success rate. "
                                f"Net: ${pnl['net_profit']:.2f}.",
                    agent="system",
                )
        except Exception as e:
            logger.debug(f"Ошибка сохранения навыков: {e}", extra={"event": "skill_save_error"})

        # 4.1 Sync capability packs into skill registry
        try:
            from modules.skill_registry import SkillRegistry
            SkillRegistry().register_from_capability_packs()
        except Exception:
            pass
        # 4.2 Write capability pack report
        try:
            import json
            root = PROJECT_ROOT / "capability_packs"
            rows = []
            for spec in root.glob("*/spec.json"):
                try:
                    data = json.loads(spec.read_text(encoding="utf-8"))
                except Exception:
                    continue
                rows.append({
                    "name": data.get("name") or spec.parent.name,
                    "category": data.get("category", ""),
                    "status": data.get("acceptance_status", "pending"),
                    "version": data.get("version", ""),
                    "risk": data.get("risk_score", 0),
                })
            rows.sort(key=lambda r: r["name"])
            out = PROJECT_ROOT / "reports" / f"CAPABILITY_PACK_REPORT_{today}.md"
            lines = [f"# Capability Pack Report ({today})", "", "| Name | Category | Status | Version | Risk |", "|---|---|---|---|---|"]
            for r in rows:
                lines.append(f"| {r['name']} | {r['category']} | {r['status']} | {r['version']} | {r['risk']} |")
            out.write_text("\\n".join(lines), encoding="utf-8")
        except Exception:
            pass

        # 5. Cleanup resolved errors older than 7 days
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
        owner_prefs = ""
        try:
            prefs = OwnerPreferenceModel().list_preferences(limit=5)
            if prefs:
                owner_prefs = "\n".join(f"- {p.get('pref_key')}: {p.get('value')}" for p in prefs)
        except Exception:
            pass

        # 3. Generate weekly plan via LLM (1 call for whole week)
        now = datetime.now(timezone.utc)
        week_dates = [(now + timedelta(days=i)).strftime("%Y-%m-%d (%A)") for i in range(7)]

        # 2.5. Strategic brainstorm for weekly plan (multi-model)
        brainstorm_context = ""
        if settings.BRAINSTORM_WEEKLY and self.judge_protocol:
            try:
                result = await self.judge_protocol.brainstorm(
                    "План на неделю: важные обновления, продажи, анализ ниш, создание продуктов, продвижение."
                )
                brainstorm_context = (result.get("final_strategy") or "")[:1200]
                if self.memory and brainstorm_context:
                    try:
                        self.memory.store_knowledge(
                            doc_id=f"weekly_brainstorm_{now.strftime('%Y-%m-%d')}",
                            text=brainstorm_context,
                            metadata={"type": "weekly_brainstorm", "date": now.strftime("%Y-%m-%d")},
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Weekly brainstorm error: {e}")

        prompt = (
            "Ты VITO — автономный AI-агент для заработка на цифровых продуктах.\n\n"
            "Создай конкретный план на неделю. Каждый день — ОДНА задача.\n"
            "Платформы: Gumroad (продукты), Printful (принты одежды), Twitter (контент), Etsy (листинги).\n\n"
            f"Стратегический брейншторм:\n{brainstorm_context or '(нет)'}\n\n"
            f"Тренды из разведки:\n{trends_context or '(нет данных)'}\n\n"
            f"Навыки:\n{skills_context or '(нет навыков)'}\n\n"
            f"Предпочтения владельца:\n{owner_prefs or '(нет)'}\n\n"
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

        # 5. Notify owner only when cron notifications are enabled
        if self._cron_notifications_enabled():
            plan_summary = "\n".join(lines[:7]) if lines else "(план не удалось распарсить)"
            await self.comms.send_message(
                f"VITO Недельный план:\n\n{plan_summary[:800]}",
                level="cron",
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
        if not self._cron_notifications_enabled():
            logger.debug("Morning report skipped (cron notifications disabled)", extra={"event": "morning_report_skipped"})
            return
        stats = self.goal_engine.get_stats()
        finance_block = self.finance.format_morning_finance()

        trends_block = ""
        try:
            if self.memory:
                trends = self.memory.search_knowledge("trend trends ниша", n_results=3)
                if trends:
                    lines = ["Горячее сегодня (тренды):"]
                    for t in trends:
                        lines.append(f"- {t['text'][:120]}")
                    trends_block = "\n".join(lines)
        except Exception:
            pass

        today_block = ""
        try:
            import sqlite3
            conn = sqlite3.connect(settings.SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT title, description FROM weekly_calendar WHERE date = ? LIMIT 1",
                (today,),
            ).fetchone()
            conn.close()
            if row:
                today_block = f"На сегодня:\n- {row['title']} — {row['description'][:200]}"
        except Exception:
            pass

        done_block = ""
        try:
            from modules.execution_facts import ExecutionFacts
            facts = ExecutionFacts()
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            since = f"{yesterday}T00:00:00+00:00"
            items = facts.facts_since(since, limit=5)
            if items:
                lines = ["Сделано вчера:"]
                for f in items:
                    detail = f.detail or f.action
                    lines.append(f"- {f.action} — {detail[:120]}")
                done_block = "\n".join(lines)
        except Exception:
            pass

        approvals_block = ""
        try:
            waiting = self.goal_engine.get_waiting_approvals()
            pending_approvals = len(waiting)
            if self.comms:
                pending_approvals += getattr(self.comms, "pending_approvals_count", lambda: 0)()
            if pending_approvals:
                lines = ["Нужно одобрение:"]
                if waiting:
                    for g in waiting[:3]:
                        lines.append(f"- {g.title[:120]}")
                approvals_block = "\n".join(lines)
        except Exception:
            pass

        report = (
            f"VITO Отчёт | {datetime.now(timezone.utc).strftime('%d.%m.%Y')}\n\n"
            f"{finance_block}\n\n"
            f"Цели: выполнено {stats['completed']}, в работе {stats['executing']}, "
            f"ожидают {stats['pending']}\n"
            f"Успешность: {stats['success_rate']:.0%}"
        )
        if trends_block:
            report += f"\n\n{trends_block}"
        if today_block:
            report += f"\n\n{today_block}"
        if done_block:
            report += f"\n\n{done_block}"
        if approvals_block:
            report += f"\n\n{approvals_block}"

        # Add balance check to morning report
        try:
            balance_block = await self._check_balances_report()
            if balance_block:
                report += f"\n\n{balance_block}"
        except Exception as e:
            logger.warning(f"Balance check in morning report failed: {e}")

        logger.info(
            f"Утренний отчёт сформирован",
            extra={"event": "morning_report", "context": {"report": report}},
        )
        await self.comms.send_morning_report(report)

    async def _check_balances_report(self) -> str:
        """Check external service balances and return formatted report block."""
        try:
            from modules.balance_checker import BalanceChecker
            checker = BalanceChecker()
            balances = await checker.check_all()

            # Check for low balances and send alerts
            alerts = checker.get_low_balance_alerts(balances)
            if alerts:
                logger.warning(f"Low balance alerts: {alerts}", extra={"event": "low_balance_alert"})

            internal = {
                "daily_spent": self.finance.get_daily_spent(),
                "daily_earned": self.finance.get_daily_earned(),
                "daily_limit": float(os.getenv("DAILY_LIMIT_USD", "3")),
            }
            return checker.format_report(balances, include_internal=internal)
        except Exception as e:
            logger.warning(f"Balance check failed: {e}", extra={"event": "balance_check_error"})
            return ""

    def _cron_notifications_enabled(self) -> bool:
        if not settings.TELEGRAM_CRON_ENABLED:
            return False
        try:
            if self.cancel_state and self.cancel_state.is_cancelled():
                return False
        except Exception:
            pass
        return True

    async def _scheduled_balance_check(self) -> None:
        """12:00 — scheduled balance check, alert only on low balances."""
        logger.info("Scheduled balance check", extra={"event": "balance_check_start"})
        try:
            from modules.balance_checker import BalanceChecker
            checker = BalanceChecker()
            balances = await checker.check_all()
            alerts = checker.get_low_balance_alerts(balances)

            if alerts:
                logger.warning(f"Low balance alerts: {alerts}", extra={"event": "low_balance_alert"})
                if self._cron_notifications_enabled():
                    msg = "VITO Balance Alert\n\n" + "\n".join(f"  {a}" for a in alerts)
                    await self.comms.send_message(msg, level="cron")
                    logger.warning(f"Low balance alerts sent: {len(alerts)}", extra={"event": "low_balance_alert_sent"})
            else:
                logger.info("All balances OK", extra={"event": "balances_ok"})
        except Exception as e:
            logger.warning(f"Scheduled balance check error: {e}", extra={"event": "balance_check_error"})

    async def _run_scheduled_task(self, task) -> None:
        """Execute scheduled task (reports/reminders)."""
        if not self._cron_notifications_enabled():
            logger.debug(
                f"Scheduled task '{task.title}' skipped (cron notifications disabled)",
                extra={"event": "scheduled_task_skipped", "context": {"task_id": task.id}},
            )
            return
        try:
            if task.action == "sales_report":
                msg = "Отчёт по продажам\n"
                if self.finance:
                    msg += self.finance.format_morning_finance()
                await self.comms.send_message(msg, level="cron")
            elif task.action == "platform_report":
                msg = "Отчёт по площадкам\n"
                try:
                    from modules.balance_checker import BalanceChecker
                    checker = BalanceChecker()
                    balances = await checker.check_all()
                    msg += checker.format_report(balances, include_internal=None)
                except Exception:
                    msg += "Нет данных по площадкам."
                await self.comms.send_message(msg, level="cron")
            elif task.action == "content_report":
                msg = "Отчёт по контенту\n"
                try:
                    # Basic placeholder: no unified content store yet
                    msg += "Нет агрегированного хранилища контента. Используй /report или уточни формат."
                except Exception:
                    pass
                await self.comms.send_message(msg, level="cron")
            elif task.action == "ads_report":
                msg = "Отчёт по рекламе\n"
                msg += "Интеграции рекламных кабинетов не настроены."
                await self.comms.send_message(msg, level="cron")
            elif task.action == "report":
                parts = ["VITO Report (Scheduled)"]
                if self.finance:
                    parts.append(self.finance.format_morning_finance())
                if self.goal_engine:
                    gs = self.goal_engine.get_stats()
                    parts.append(
                        f"Цели: {gs['completed']} выполнено, {gs['executing']} в работе, "
                        f"{gs['pending']} ожидают\nУспешность: {gs['success_rate']:.0%}"
                    )
                await self.comms.send_message("\n\n".join(parts), level="cron")
            else:
                await self.comms.send_message(f"Напоминание: {task.title}", level="cron")
        except Exception as e:
            logger.warning(f"Scheduled task error: {e}", extra={"event": "scheduled_task_error"})

    async def _proactive_check(self) -> None:
        """v0.3.0: Проактивная проверка каждые 4 часа — делится достижениями, предлагает шаги."""
        if not settings.PROACTIVE_ENABLED:
            return
        try:
            if self.cancel_state and self.cancel_state.is_cancelled():
                logger.debug("Proactive check skipped (owner paused via /cancel)", extra={"event": "proactive_paused"})
                return
        except Exception:
            pass
        if not self._cron_notifications_enabled():
            logger.debug("Proactive check skipped (cron notifications disabled)", extra={"event": "proactive_check_skipped"})
            return
        logger.info("Проактивная проверка", extra={"event": "proactive_check_start"})
        try:
            stats = self.goal_engine.get_stats()
            completed_today = stats.get("completed", 0)

            if completed_today > 0:
                await self.comms.send_message(
                    f"VITO Проактивный отчёт\n\n"
                    f"Выполнено целей: {completed_today}\n"
                    f"Потрачено: ${self.llm_router.get_daily_spend():.2f}\n"
                    f"Рекомендую: продолжать работу по текущим целям.",
                    level="cron",
                )

            # Предложение следующих шагов если нет задач
            pending = stats.get("pending", 0)
            executing = stats.get("executing", 0)
            if pending == 0 and executing == 0:
                await self.comms.send_message(
                    "VITO: Нет активных задач. Предлагаю:\n"
                    "1. /trends — просканировать новые тренды\n"
                    "2. /deep <тема> — анализ перспективной ниши\n"
                    "3. /goal <задача> — создать новую цель",
                    level="cron",
                )

        except Exception as e:
            logger.warning(f"Проактивная проверка ошибка: {e}", extra={"event": "proactive_check_error"})

    # ── Shutdown ──

    async def shutdown(self) -> None:
        """Корректное завершение всех подсистем."""
        was_running = bool(self.running)
        self.running = False
        logger.info("VITO завершает работу...", extra={"event": "shutdown_start", "context": {"was_running": was_running}})
        try:
            self.decision_loop.stop()
        except Exception:
            pass
        try:
            await self.registry.stop_all()
        except Exception:
            pass
        try:
            await self.comms.stop()
        except Exception:
            pass
        try:
            await self._close_platform_sessions()
        except Exception:
            pass
        try:
            self.finance.close()
        except Exception:
            pass
        try:
            await self.memory.close()
        except Exception:
            pass
        logger.info("VITO остановлен", extra={"event": "shutdown_complete"})

    async def _close_platform_sessions(self) -> None:
        """Close aiohttp-backed platform sessions to avoid leaked connectors."""
        candidates = []
        for name in ("_platforms_commerce", "_platforms_social"):
            m = getattr(self, name, None)
            if isinstance(m, dict):
                candidates.extend(list(m.values()))
        for name in ("_image_generator", "_youtube", "_twitter"):
            obj = getattr(self, name, None)
            if obj is not None:
                candidates.append(obj)

        seen: set[int] = set()
        for obj in candidates:
            try:
                oid = id(obj)
                if oid in seen:
                    continue
                seen.add(oid)
                close_fn = getattr(obj, "close", None)
                if close_fn is None:
                    continue
                res = close_fn()
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                continue


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
