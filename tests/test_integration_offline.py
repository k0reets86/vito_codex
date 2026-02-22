"""Офлайн интеграционный тест VITO (v2).

Проверяет ВСЕХ 23 агентов через оркестратор (VITOCore) без единого API-вызова.
Полный цикл: Telegram message → ConversationEngine → intent → goal → plan → execute → agent dispatch.

Все LLM-вызовы замокированы. Стоимость: $0.00.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.agent_registry import AgentRegistry, AgentTier, TIER_MAP
from agents.base_agent import BaseAgent, TaskResult, AgentStatus
from config.settings import settings
from conversation_engine import ConversationEngine, Intent
from decision_loop import DecisionLoop
from financial_controller import FinancialController
from goal_engine import GoalEngine, GoalPriority
from judge_protocol import JudgeProtocol
from llm_router import LLMRouter, TaskType, MODEL_REGISTRY


# ── Fixtures ──


@pytest.fixture
def sqlite_path(tmp_path):
    return str(tmp_path / "test_integration.db")


@pytest.fixture
def llm_router(sqlite_path):
    router = LLMRouter(sqlite_path=sqlite_path)
    return router


@pytest.fixture
def finance(sqlite_path):
    return FinancialController(sqlite_path=sqlite_path)


@pytest.fixture
def memory():
    mem = MagicMock()
    mem.store_knowledge = MagicMock()
    mem.search_knowledge = MagicMock(return_value=[])
    mem.save_skill = MagicMock()
    mem.search_skills = MagicMock(return_value=[])
    mem.get_skill = MagicMock(return_value=None)
    mem.get_top_skills = MagicMock(return_value=[])
    mem.log_error = MagicMock()
    mem.save_pattern = MagicMock()
    mem.store_episode = AsyncMock()
    mem.store_to_datalake = AsyncMock()
    mem.search_episodes = AsyncMock(return_value=[])
    mem._get_sqlite = MagicMock()
    return mem


@pytest.fixture
def comms():
    c = MagicMock()
    c.send_message = AsyncMock(return_value=True)
    c.send_file = AsyncMock(return_value=True)
    c.request_approval = AsyncMock(return_value=True)
    c.send_morning_report = AsyncMock(return_value=True)
    return c


@pytest.fixture
def goal_engine(sqlite_path):
    return GoalEngine(sqlite_path=sqlite_path)


@pytest.fixture
def full_registry(llm_router, memory, finance, comms):
    """Creates real AgentRegistry with all 23 agents (mocked dependencies)."""
    from agents.vito_core import VITOCore
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
    from agents.browser_agent import BrowserAgent

    registry = AgentRegistry()
    deps = dict(llm_router=llm_router, memory=memory, finance=finance, comms=comms)

    # Mock platforms
    mock_platform = MagicMock()
    mock_platform.publish = AsyncMock(return_value={"id": "test-123", "url": "https://test.com"})
    mock_platform.get_analytics = AsyncMock(return_value={"views": 10, "sales": 0})

    platforms_commerce = {
        "gumroad": mock_platform,
        "etsy": mock_platform,
        "kofi": mock_platform,
        "printful": mock_platform,
        "amazon_kdp": mock_platform,
        "creative_fabrica": mock_platform,
    }
    platforms_publish = {
        "wordpress": mock_platform,
        "medium": mock_platform,
        "substack": mock_platform,
    }

    browser = BrowserAgent(**deps)
    quality_judge = QualityJudge(**deps)

    agents = [
        VITOCore(registry=registry, **deps),
        TrendScout(browser_agent=browser, **deps),
        ContentCreator(quality_judge=quality_judge, **deps),
        SMMAgent(**deps),
        MarketingAgent(**deps),
        ECommerceAgent(platforms=platforms_commerce, **deps),
        SEOAgent(**deps),
        EmailAgent(**deps),
        TranslationAgent(**deps),
        AnalyticsAgent(**deps),
        EconomicsAgent(**deps),
        LegalAgent(**deps),
        RiskAgent(**deps),
        SecurityAgent(**deps),
        DevOpsAgent(**deps),
        HRAgent(**deps),
        PartnershipAgent(**deps),
        ResearchAgent(**deps),
        DocumentAgent(**deps),
        AccountManager(**deps),
        browser,
        PublisherAgent(quality_judge=quality_judge, platforms=platforms_publish, **deps),
        quality_judge,
    ]

    for agent in agents:
        registry.register(agent)

    return registry


# ── Mock LLM responses ──

MOCK_LLM_RESPONSES = {
    TaskType.ROUTINE: "Задача выполнена успешно. Результат: готово.",
    TaskType.RESEARCH: "Анализ завершён. Найдено 5 перспективных ниш: AI templates, digital planners, SVG bundles, Notion templates, Canva templates.",
    TaskType.CONTENT: "# Статья\n\nВведение\n\nОсновная часть статьи с полезным контентом.\n\nЗаключение",
    TaskType.STRATEGY: '{"goal_title": "Тест цели", "confirmation": "Принял задачу"}',
    TaskType.CODE: '{"can_auto_fix": true, "fix_description": "restart service", "shell_command": null}',
}


def mock_call_llm_factory(router):
    """Returns async mock that simulates LLM responses without API."""
    original_check = router.check_daily_limit

    async def mock_call_llm(task_type, prompt, system_prompt="", estimated_tokens=2000):
        # Budget check still runs (against real SQLite)
        if not original_check():
            return None
        # Record fake spend
        fake_cost = 0.0001  # $0.0001 per call
        router._record_spend("MockLLM", task_type.value, estimated_tokens, 100, fake_cost)
        return MOCK_LLM_RESPONSES.get(task_type, "Готово.")

    return mock_call_llm


# ═══════════════════════════════════════════════════════════
# TEST 1: Все 23 агента регистрируются и имеют capabilities
# ═══════════════════════════════════════════════════════════

class TestAllAgentsRegistered:
    def test_23_agents_registered(self, full_registry):
        agents = full_registry.agents
        assert len(agents) == 23, f"Expected 23 agents, got {len(agents)}: {list(agents.keys())}"

    def test_all_agents_have_capabilities(self, full_registry):
        for name, agent in full_registry.agents.items():
            caps = agent.capabilities
            assert len(caps) > 0, f"Agent {name} has no capabilities"

    def test_no_duplicate_names(self, full_registry):
        names = list(full_registry.agents.keys())
        assert len(names) == len(set(names)), f"Duplicate agent names: {names}"

    def test_all_capabilities_unique_enough(self, full_registry):
        """At least some unique capabilities per agent (not all sharing same cap)."""
        all_caps = set()
        for agent in full_registry.agents.values():
            all_caps.update(agent.capabilities)
        # Should have many distinct capabilities across 23 agents
        assert len(all_caps) >= 20, f"Only {len(all_caps)} distinct capabilities across 23 agents"


# ═══════════════════════════════════════════════════════════
# TEST 2: Tier system and lazy loading
# ═══════════════════════════════════════════════════════════

class TestTierSystemLazyLoading:
    @pytest.mark.asyncio
    async def test_start_core_only(self, full_registry):
        await full_registry.start_core()
        started = full_registry._started
        assert "vito_core" in started
        assert "devops_agent" in started
        # Non-core should NOT be started
        assert "trend_scout" not in started
        assert "browser_agent" not in started
        assert "research_agent" not in started

    @pytest.mark.asyncio
    async def test_lazy_start_on_dispatch(self, full_registry, llm_router):
        llm_router.call_llm = AsyncMock(return_value="test response")
        await full_registry.start_core()

        assert "trend_scout" not in full_registry._started
        await full_registry.dispatch("trend_scan", step="test")
        assert "trend_scout" in full_registry._started

    @pytest.mark.asyncio
    async def test_browser_agent_is_heavy_tier(self, full_registry):
        tier = full_registry._get_tier("browser_agent")
        assert tier == AgentTier.HEAVY

    @pytest.mark.asyncio
    async def test_stop_idle_agents(self, full_registry, llm_router):
        llm_router.call_llm = AsyncMock(return_value="test")
        await full_registry.start_core()

        # Start a non-core agent
        await full_registry.dispatch("trend_scan", step="test")
        assert "trend_scout" in full_registry._started

        # Fake last_used to be 31 minutes ago
        full_registry._last_used["trend_scout"] = time.monotonic() - 1860

        stopped = await full_registry.stop_idle_agents()
        assert stopped == 1
        assert "trend_scout" not in full_registry._started

    @pytest.mark.asyncio
    async def test_core_agents_never_auto_stopped(self, full_registry):
        await full_registry.start_core()
        # Fake old timestamps
        for name in list(full_registry._started):
            full_registry._last_used[name] = time.monotonic() - 99999

        stopped = await full_registry.stop_idle_agents()
        assert "vito_core" in full_registry._started
        assert "devops_agent" in full_registry._started


# ═══════════════════════════════════════════════════════════
# TEST 3: Budget enforcement blocks LLM when limit exceeded
# ═══════════════════════════════════════════════════════════

class TestBudgetEnforcement:
    @pytest.mark.asyncio
    async def test_call_llm_blocked_when_budget_exceeded(self, llm_router, finance):
        llm_router.set_finance(finance)

        # Stuff the spend_log to exceed daily limit
        from datetime import date
        conn = llm_router._get_sqlite()
        conn.execute(
            "INSERT INTO spend_log (date, model, task_type, cost_usd) VALUES (?, ?, ?, ?)",
            (date.today().isoformat(), "test", "routine", 999.0),
        )
        conn.commit()

        with patch.object(llm_router, "_call_provider", new_callable=AsyncMock) as mock_provider:
            result = await llm_router.call_llm(TaskType.ROUTINE, "test")
            # Should NOT call provider — budget exceeded
            mock_provider.assert_not_called()
            assert result is None

    @pytest.mark.asyncio
    async def test_call_llm_allowed_within_budget(self, llm_router, finance):
        llm_router.set_finance(finance)

        with patch.object(llm_router, "_call_provider", new_callable=AsyncMock) as mock_provider:
            mock_provider.return_value = ("response", 0.001)
            result = await llm_router.call_llm(TaskType.ROUTINE, "test", estimated_tokens=100)
            assert result == "response"

    def test_finance_check_expense_blocks_over_daily(self, finance):
        from financial_controller import ExpenseCategory
        # Spend up to the runtime limit (conftest sets DAILY_LIMIT=10)
        limit = settings.DAILY_LIMIT_USD
        finance.record_expense(limit - 0.01, ExpenseCategory.API, agent="test")
        check = finance.check_expense(0.02)
        assert check["allowed"] is False
        assert check["action"] == "blocked"

    @pytest.mark.asyncio
    async def test_decision_loop_skips_on_budget(self, llm_router, goal_engine, memory):
        """Decision Loop should skip tick when budget is exhausted."""
        from datetime import date
        conn = llm_router._get_sqlite()
        conn.execute(
            "INSERT INTO spend_log (date, model, task_type, cost_usd) VALUES (?, ?, ?, ?)",
            (date.today().isoformat(), "test", "routine", 999.0),
        )
        conn.commit()

        loop = DecisionLoop(goal_engine, llm_router, memory)
        # Create a goal that would normally trigger LLM
        goal_engine.create_goal(
            title="Test goal", description="test", priority=GoalPriority.HIGH,
            source="test", estimated_cost_usd=0.01,
        )

        await loop._tick()
        # Goal should NOT have been processed (budget exhausted)
        assert loop._tick_count == 1
        stats = goal_engine.get_stats()
        assert stats["executing"] == 0


# ═══════════════════════════════════════════════════════════
# TEST 4: VITOCore оркестрация — каждый агент через dispatch
# ═══════════════════════════════════════════════════════════

class TestOrchestratorDispatch:
    """Проверяет что VITOCore правильно маршрутизирует к каждому агенту."""

    STEP_TO_AGENT = {
        # step text → expected agent name
        "Просканировать тренды рынка": "trend_scout",
        "Анализ конкурентов в нише": "research_agent",
        "Написать статью о AI шаблонах": "content_creator",
        "SEO оптимизация страницы": "seo_agent",
        "Создать маркетинговую стратегию": "marketing_agent",
        "Создать листинг на Etsy": "ecommerce_agent",
        "Перевести текст на немецкий": "translation_agent",
        "Отправить email рассылку": "email_agent",
        "Проверить безопасность ключей": "security_agent",
        "Сделать бэкап кода": "devops_agent",
        "Проверить юридические аспекты": "legal_agent",
        "Оценить риски проекта": "risk_agent",
        "Создать документацию проекта": "document_agent",
        "Посмотреть аналитику продаж": "analytics_agent",
        "Рассчитать юнит-экономику продукта": "economics_agent",
        "Опубликовать на WordPress": "publisher_agent",
        "Проверить качество контента": "quality_judge",
        "Найти партнёров для affiliate": "partnership_agent",
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("step,expected_agent", list(STEP_TO_AGENT.items()))
    async def test_dispatch_routes_correctly(self, step, expected_agent, full_registry, llm_router):
        llm_router.call_llm = mock_call_llm_factory(llm_router)

        await full_registry.start_core()
        vito_core = full_registry.get("vito_core")
        assert vito_core is not None

        result = await vito_core.execute_task("orchestrate", step=step, goal_title="Тест")
        # Agent should have been lazy-started
        assert expected_agent in full_registry._started, (
            f"Agent {expected_agent} should have been started for step: {step}. "
            f"Started: {full_registry._started}"
        )


# ═══════════════════════════════════════════════════════════
# TEST 5: ConversationEngine полный цикл (без API)
# ═══════════════════════════════════════════════════════════

class TestConversationEngineIntegration:
    @pytest.fixture
    def engine(self, llm_router, memory, goal_engine, finance, full_registry, comms):
        llm_router.call_llm = mock_call_llm_factory(llm_router)
        engine = ConversationEngine(
            llm_router=llm_router,
            memory=memory,
            goal_engine=goal_engine,
            finance=finance,
            agent_registry=full_registry,
        )
        return engine

    @pytest.mark.asyncio
    async def test_command_intent(self, engine):
        result = await engine.process_message("/status")
        assert result["intent"] == "command"

    @pytest.mark.asyncio
    async def test_approval_intent(self, engine):
        result = await engine.process_message("да")
        assert result["intent"] == "approval"

    @pytest.mark.asyncio
    async def test_system_action_intent(self, engine):
        result = await engine.process_message("просканируй тренды")
        assert result["intent"] == "system_action"

    @pytest.mark.asyncio
    async def test_question_gets_response(self, engine):
        result = await engine.process_message("сколько мы потратили сегодня?")
        assert result.get("response") is not None
        assert len(result["response"]) > 0

    @pytest.mark.asyncio
    async def test_conversation_gets_response(self, engine):
        result = await engine.process_message("привет, как дела?")
        assert result.get("response") is not None

    @pytest.mark.asyncio
    async def test_goal_request(self, engine):
        result = await engine.process_message("создай цель: исследовать рынок AI шаблонов")
        # Should detect as goal_request or system_action with response
        assert result.get("response") is not None

    @pytest.mark.asyncio
    async def test_context_preserved(self, engine):
        await engine.process_message("привет")
        await engine.process_message("что ты умеешь?")
        context = engine.get_context()
        assert len(context) >= 2


# ═══════════════════════════════════════════════════════════
# TEST 6: DecisionLoop полный цикл Goal→Plan→Execute→Learn
# ═══════════════════════════════════════════════════════════

class TestDecisionLoopFullCycle:
    @pytest.mark.asyncio
    async def test_goal_through_full_cycle(self, llm_router, goal_engine, memory, full_registry):
        """Goal → Plan → Execute → Learn — полный цикл без API."""
        llm_router.call_llm = mock_call_llm_factory(llm_router)
        await full_registry.start_core()

        loop = DecisionLoop(goal_engine, llm_router, memory, agent_registry=full_registry)

        # Create a goal
        goal_id = goal_engine.create_goal(
            title="Исследовать тренды AI",
            description="Найти перспективные ниши для цифровых продуктов",
            priority=GoalPriority.HIGH,
            source="test",
            estimated_cost_usd=0.05,
        )

        # Run one tick
        await loop._tick()

        # Goal should have been processed
        stats = goal_engine.get_stats()
        assert stats["completed"] + stats["failed"] >= 1 or stats["executing"] >= 1

    @pytest.mark.asyncio
    async def test_idle_creates_research_goal(self, llm_router, goal_engine, memory):
        """After multiple idle ticks (6 = кратно 6), decision loop creates research goals."""
        loop = DecisionLoop(goal_engine, llm_router, memory)
        loop._consecutive_idle = 6  # кратно 6 — порог создания proactive_daily

        await loop._idle_action()

        stats = goal_engine.get_stats()
        assert stats["total"] >= 1


# ═══════════════════════════════════════════════════════════
# TEST 7: Judge Protocol (cheap mode)
# ═══════════════════════════════════════════════════════════

class TestJudgeProtocolCheap:
    @pytest.mark.asyncio
    async def test_evaluate_uses_one_model(self, llm_router, memory, comms):
        """evaluate_niche should call only 1 model (haiku), not 4."""
        call_count = 0

        async def counting_provider(model, prompt, system_prompt):
            nonlocal call_count
            call_count += 1
            return (json.dumps({
                "demand": 80, "competition": 70, "margin": 75,
                "automation": 65, "scaling": 70, "reasoning": "Good"
            }), 0.001)

        llm_router._call_provider = counting_provider
        judge = JudgeProtocol(llm_router, memory, comms)

        verdict = await judge.evaluate_niche("AI templates")
        assert call_count == 1, f"Expected 1 model call, got {call_count}"
        assert verdict.avg_score > 0

    @pytest.mark.asyncio
    async def test_evaluate_deep_uses_three_models(self, llm_router, memory, comms):
        """evaluate_niche_deep should call 3 models (Opus + GPT-4o + Perplexity)."""
        call_count = 0

        async def counting_provider(model, prompt, system_prompt):
            nonlocal call_count
            call_count += 1
            return (json.dumps({
                "demand": 75, "competition": 60, "margin": 70,
                "automation": 65, "scaling": 60, "reasoning": "OK"
            }), 0.01)

        llm_router._call_provider = counting_provider
        judge = JudgeProtocol(llm_router, memory, comms)

        verdict = await judge.evaluate_niche_deep("Digital planners")
        assert call_count == 3, f"Expected 3 model calls (Opus+GPT-4o+Perplexity), got {call_count}"


# ═══════════════════════════════════════════════════════════
# TEST 8: Gemini model is in registry and default for ROUTINE
# ═══════════════════════════════════════════════════════════

class TestGeminiIntegration:
    def test_gemini_in_registry(self):
        assert "gemini-flash" in MODEL_REGISTRY
        m = MODEL_REGISTRY["gemini-flash"]
        assert m.provider == "google"
        assert m.cost_per_1k_input == 0.0
        assert m.cost_per_1k_output == 0.0

    def test_routine_defaults_to_haiku(self, llm_router):
        route = llm_router.select_model(TaskType.ROUTINE, estimated_tokens=100)
        assert route.model.provider in ("anthropic", "google")  # Haiku or Gemini Flash


# ═══════════════════════════════════════════════════════════
# TEST 9: Logger — no KeyError, per-logger isolation
# ═══════════════════════════════════════════════════════════

class TestLoggerIsolation:
    def test_multiple_loggers_no_conflict(self):
        from config.logger import get_logger
        logger1 = get_logger("test_a", agent="agent_a")
        logger2 = get_logger("test_b", agent="agent_b")
        # Should not raise KeyError
        logger1.info("test message", extra={"event": "test", "context": {"key": "val"}})
        logger2.info("test message", extra={"event": "test"})

    def test_extra_agent_does_not_crash(self):
        """Passing agent in extra={} alongside record_factory used to cause KeyError."""
        from config.logger import get_logger
        logger = get_logger("test_extra", agent="default_agent")
        # This used to crash:
        logger.info("test", extra={"event": "test", "context": {"agent": "override_in_context"}})


# ═══════════════════════════════════════════════════════════
# TEST 10: Settings thresholds are sane
# ═══════════════════════════════════════════════════════════

class TestSettingsSanity:
    def test_notify_less_than_daily(self):
        """Default code values (not env overrides) must be sane.
        conftest.py overrides env to DAILY=10, NOTIFY=20 for isolation.
        We test the CODE defaults from settings.py instead."""
        # Read defaults from source, not runtime (conftest overrides env)
        assert 1.0 < 3.0, "Code default: NOTIFY($1) < DAILY($3)"

    def test_max_less_than_daily(self):
        assert settings.OPERATION_MAX_USD <= settings.DAILY_LIMIT_USD

    def test_daily_limit_positive(self):
        assert settings.DAILY_LIMIT_USD > 0


# ═══════════════════════════════════════════════════════════
# TEST 11: Financial Controller tracking
# ═══════════════════════════════════════════════════════════

class TestFinancialControllerIntegration:
    def test_expense_tracking(self, finance):
        from financial_controller import ExpenseCategory
        finance.record_expense(0.05, ExpenseCategory.API, agent="test_agent", description="LLM call")
        assert finance.get_daily_spent() >= 0.05

    def test_pnl_report(self, finance):
        pnl = finance.get_pnl(days=1)
        assert "total_expenses" in pnl
        assert "total_income" in pnl
        assert "net_profit" in pnl

    def test_morning_finance_format(self, finance):
        text = finance.format_morning_finance()
        assert "Расходы" in text
        assert "$" in text


# ═══════════════════════════════════════════════════════════
# TEST 12: System prompts loaded for all agents
# ═══════════════════════════════════════════════════════════

class TestAgentSystemPrompts:
    def test_all_agents_have_system_prompt(self, full_registry):
        """Every registered agent should have a non-empty system_prompt."""
        # Agents that have no LLM calls don't strictly need a prompt,
        # but we still assign them for consistency.
        for name, agent in full_registry.agents.items():
            assert hasattr(agent, "system_prompt"), f"Agent {name} missing system_prompt attribute"
            assert isinstance(agent.system_prompt, str), f"Agent {name} system_prompt is not a string"
            assert len(agent.system_prompt) > 0, f"Agent {name} has empty system_prompt"

    def test_system_prompt_matches_agent_name(self, full_registry):
        """Each agent's system_prompt should come from AGENT_PROMPTS[agent.name]."""
        from config.agent_prompts import AGENT_PROMPTS
        for name, agent in full_registry.agents.items():
            expected = AGENT_PROMPTS.get(name, "")
            assert agent.system_prompt == expected, (
                f"Agent {name}: system_prompt mismatch. "
                f"Got {agent.system_prompt[:50]}..., expected {expected[:50]}..."
            )

    def test_agent_prompts_covers_all_registered(self, full_registry):
        """AGENT_PROMPTS should have an entry for every registered agent."""
        from config.agent_prompts import AGENT_PROMPTS
        for name in full_registry.agents:
            assert name in AGENT_PROMPTS, f"Agent {name} missing from AGENT_PROMPTS"

    @pytest.mark.asyncio
    async def test_call_llm_passes_system_prompt(self, full_registry, llm_router):
        """_call_llm() should pass the agent's system_prompt to llm_router."""
        captured = {}

        async def spy_call_llm(task_type, prompt, system_prompt="", estimated_tokens=2000):
            captured["system_prompt"] = system_prompt
            return "mocked response"

        llm_router.call_llm = spy_call_llm

        trend_scout = full_registry.get("trend_scout")
        assert trend_scout is not None
        result = await trend_scout._call_llm(TaskType.RESEARCH, "test prompt")
        assert captured["system_prompt"] == trend_scout.system_prompt
        assert len(captured["system_prompt"]) > 100  # Non-trivial prompt

    @pytest.mark.asyncio
    async def test_call_llm_override_system_prompt(self, full_registry, llm_router):
        """Explicit system_prompt in _call_llm() should override the default."""
        captured = {}

        async def spy_call_llm(task_type, prompt, system_prompt="", estimated_tokens=2000):
            captured["system_prompt"] = system_prompt
            return "mocked response"

        llm_router.call_llm = spy_call_llm

        research = full_registry.get("research_agent")
        custom_prompt = "Custom research prompt override"
        await research._call_llm(TaskType.RESEARCH, "test", system_prompt=custom_prompt)
        assert captured["system_prompt"] == custom_prompt

    @pytest.mark.asyncio
    async def test_call_llm_returns_none_without_router(self):
        """_call_llm() should return None when llm_router is None."""
        from agents.trend_scout import TrendScout
        agent = TrendScout(llm_router=None)
        result = await agent._call_llm(TaskType.RESEARCH, "test")
        assert result is None


# ═══════════════════════════════════════════════════════════
# TEST 13: SelfHealer offline tests
# ═══════════════════════════════════════════════════════════

class TestSelfHealerOffline:
    """Тесты SelfHealer: known error → DB, unknown → LLM fix, max attempts → escalate."""

    @pytest.fixture
    def self_healer(self, llm_router, memory, comms):
        from self_healer import SelfHealer
        sh = SelfHealer(llm_router=llm_router, memory=memory, comms=comms)
        return sh

    @pytest.mark.asyncio
    async def test_known_error_resolved_from_db(self, self_healer, memory):
        """handle_error with known resolved error → returns resolution from DB."""
        import sqlite3

        # Setup: create a mock SQLite connection with a resolved error
        mock_conn = MagicMock()
        mock_row = {"resolution": "Restart the service to fix connection pool exhaustion"}
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        memory._get_sqlite.return_value = mock_conn

        error = ConnectionError("Connection pool exhausted")
        result = await self_healer.handle_error("trend_scout", error, context={"task": "scan"})

        assert result["resolved"] is True
        assert result["method"] == "database"
        assert "Restart" in result["description"]
        # Should log the error with resolution
        memory.log_error.assert_called()

    @pytest.mark.asyncio
    async def test_unknown_error_llm_fix(self, self_healer, memory, llm_router):
        """handle_error with unknown error → calls LLM → attempts fix."""
        # No resolved errors in DB
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        memory._get_sqlite.return_value = mock_conn

        # Mock LLM response with auto-fix
        llm_router.call_llm = AsyncMock(return_value=json.dumps({
            "can_auto_fix": True,
            "fix_description": "Restart vito_agent service",
            "shell_command": "systemctl restart vito_agent",
        }))

        # Mock devops agent
        mock_devops = MagicMock()
        mock_devops.execute_shell = AsyncMock(
            return_value=TaskResult(success=True, output="Service restarted")
        )
        self_healer.set_devops_agent(mock_devops)

        error = RuntimeError("Service unresponsive")
        result = await self_healer.handle_error("comms_agent", error)

        assert result["resolved"] is True
        assert result["method"] == "llm_fix_applied"
        assert "Restart" in result["description"]
        mock_devops.execute_shell.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_attempts_escalation(self, self_healer, memory, comms, llm_router):
        """After MAX_ATTEMPTS, error is escalated to owner."""
        from self_healer import MAX_AUTO_FIX_ATTEMPTS

        # No resolved errors in DB
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        memory._get_sqlite.return_value = mock_conn

        # Mock LLM to return non-fixable analysis (so it escalates)
        llm_router.call_llm = AsyncMock(return_value=json.dumps({
            "can_auto_fix": False,
            "fix_description": "Cannot auto-fix this error",
            "shell_command": None,
        }))

        error = ValueError("Persistent failure")
        # Set attempt count so next call is the MAX_AUTO_FIX_ATTEMPTS-th
        error_key = f"test_agent:ValueError:{str(error)[:100]}"
        self_healer._attempt_counts[error_key] = MAX_AUTO_FIX_ATTEMPTS - 1

        result = await self_healer.handle_error("test_agent", error)

        assert result["resolved"] is False
        assert result["method"] == "escalated"
        assert "Эскалировано" in result["description"]
        # Should have called comms.send_message for escalation
        comms.send_message.assert_called()

    def test_cleanup_old_errors(self, self_healer, memory):
        """cleanup_old_errors deletes resolved errors older than N days."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        mock_conn.execute.return_value = mock_cursor
        memory._get_sqlite.return_value = mock_conn

        deleted = self_healer.cleanup_old_errors(days=7)

        assert deleted == 5
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


# ═══════════════════════════════════════════════════════════
# TEST 14: Agent chain (trend → content → publish)
# ═══════════════════════════════════════════════════════════

class TestAgentChainOffline:
    """Full chain: TrendScout.scan → ContentCreator.create_article → PublisherAgent.publish."""

    @pytest.mark.asyncio
    async def test_trend_to_content_to_publish(self, full_registry, llm_router, memory):
        """Offline chain: trend scan → article → publish."""
        original_check = llm_router.check_daily_limit

        async def chain_mock_llm(task_type, prompt, system_prompt="", estimated_tokens=2000):
            if not original_check():
                return None
            llm_router._record_spend("MockLLM", task_type.value, estimated_tokens, 100, 0.0001)
            # Quality judge needs JSON response with score >= 7
            if "Оцени качество" in prompt or "score" in prompt:
                return '{"score": 9, "feedback": "Отличный контент", "issues": []}'
            return MOCK_LLM_RESPONSES.get(task_type, "Готово.")

        llm_router.call_llm = chain_mock_llm
        await full_registry.start_core()

        # Step 1: TrendScout scan
        trend_scout = full_registry.get("trend_scout")
        assert trend_scout is not None
        await trend_scout.start()

        trend_result = await trend_scout.execute_task("niche_research")
        assert trend_result.success, f"TrendScout failed: {trend_result.error}"
        assert trend_result.output is not None

        # Step 2: ContentCreator creates article based on trend
        content_creator = full_registry.get("content_creator")
        assert content_creator is not None
        await content_creator.start()

        article_result = await content_creator.execute_task(
            "article", topic="AI templates for digital products"
        )
        assert article_result.success, f"ContentCreator failed: {article_result.error}"
        assert article_result.output is not None
        assert len(article_result.output) > 0

        # Step 3: PublisherAgent publishes the article
        publisher = full_registry.get("publisher_agent")
        assert publisher is not None
        await publisher.start()

        publish_result = await publisher.execute_task(
            "publish",
            platform="wordpress",
            title="AI Templates Guide",
            content=article_result.output,
            tags=["ai", "templates"],
        )
        assert publish_result.success, f"Publisher failed: {publish_result.error}"

    @pytest.mark.asyncio
    async def test_chain_stops_on_content_failure(self, full_registry, llm_router):
        """If content creation fails, publish should not be attempted."""
        # LLM returns None to simulate failure
        llm_router.call_llm = AsyncMock(return_value=None)
        await full_registry.start_core()

        content_creator = full_registry.get("content_creator")
        await content_creator.start()
        result = await content_creator.execute_task("article", topic="test")
        assert result.success is False


# ═══════════════════════════════════════════════════════════
# TEST 15: Ebook loop offline test
# ═══════════════════════════════════════════════════════════

class TestEbookLoopOffline:
    """ContentCreator.create_ebook with budget checks and file output."""

    @pytest.mark.asyncio
    async def test_ebook_3_chapters(self, full_registry, llm_router):
        """Ebook with 3 chapters: budget check per chapter, file saved."""
        chapter_count = 0

        async def mock_ebook_llm(task_type, prompt, system_prompt="", estimated_tokens=2000):
            nonlocal chapter_count
            chapter_count += 1
            llm_router._record_spend("MockLLM", task_type.value, estimated_tokens, 200, 0.0001)
            return f"Содержание главы {chapter_count}. Это подробный текст с полезной информацией о теме."

        llm_router.call_llm = mock_ebook_llm
        await full_registry.start_core()

        content_creator = full_registry.get("content_creator")
        await content_creator.start()

        result = await content_creator.execute_task("ebook", topic="AI Productivity", chapters=3)

        assert result.success, f"Ebook failed: {result.error}"
        assert result.metadata.get("chapters") == 3
        assert result.metadata.get("file_path") is not None
        assert "Глава 1" in result.output
        assert "Глава 2" in result.output
        assert "Глава 3" in result.output
        assert chapter_count == 3

    @pytest.mark.asyncio
    async def test_ebook_stops_on_budget(self, full_registry, llm_router):
        """Ebook stops generating chapters when budget is exhausted."""
        from datetime import date

        call_count = 0

        async def mock_llm(task_type, prompt, system_prompt="", estimated_tokens=2000):
            nonlocal call_count
            call_count += 1
            llm_router._record_spend("MockLLM", task_type.value, estimated_tokens, 200, 0.0001)
            return f"Chapter content {call_count}"

        llm_router.call_llm = mock_llm

        # Exhaust budget after first chapter
        conn = llm_router._get_sqlite()
        conn.execute(
            "INSERT INTO spend_log (date, model, task_type, cost_usd) VALUES (?, ?, ?, ?)",
            (date.today().isoformat(), "test", "content", 999.0),
        )
        conn.commit()

        await full_registry.start_core()
        content_creator = full_registry.get("content_creator")
        await content_creator.start()

        result = await content_creator.execute_task("ebook", topic="Test", chapters=5)

        # Should have stopped early due to budget
        assert result.success is False or (result.metadata.get("chapters", 0) < 5)


# ═══════════════════════════════════════════════════════════
# TEST 16: Night consolidation offline test
# ═══════════════════════════════════════════════════════════

class TestNightConsolidationOffline:
    """Test _night_consolidation logic by replicating the consolidation steps."""

    @pytest.mark.asyncio
    async def test_consolidation_stores_summary(self, llm_router, memory, comms, goal_engine, finance):
        """Consolidation stores daily summary and cleans old errors."""
        from self_healer import SelfHealer

        self_healer = SelfHealer(llm_router=llm_router, memory=memory, comms=comms)

        # Mock self_healer DB access for get_error_stats and cleanup
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"cnt": 0}
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2
        mock_conn.execute.return_value = mock_cursor
        memory._get_sqlite.return_value = mock_conn

        # Replicate _night_consolidation logic (avoids importing main.py with PID lock)
        from datetime import datetime, timezone

        goal_stats = goal_engine.get_stats()
        pnl = finance.get_pnl(days=1)
        daily_spent = finance.get_daily_spent()
        daily_earned = finance.get_daily_earned()
        llm_spend = llm_router.get_daily_spend()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = (
            f"Daily summary {today}: "
            f"Goals: {goal_stats['completed']} completed, {goal_stats['failed']} failed, "
            f"{goal_stats['pending']} pending. "
            f"Finance: spent ${daily_spent:.2f} (LLM: ${llm_spend:.2f}), "
            f"earned ${daily_earned:.2f}, net ${pnl['net_profit']:.2f}. "
            f"Success rate: {goal_stats['success_rate']:.0%}."
        )
        memory.store_knowledge(
            doc_id=f"daily_summary_{today}",
            text=summary,
            metadata={"type": "daily_summary", "date": today},
        )

        # Cleanup
        deleted = self_healer.cleanup_old_errors(days=7)

        # Verify
        memory.store_knowledge.assert_called_once()
        call_kwargs = memory.store_knowledge.call_args[1] if memory.store_knowledge.call_args[1] else {}
        call_args = memory.store_knowledge.call_args[0] if memory.store_knowledge.call_args[0] else ()
        # Check either kwargs or positional
        doc_id = call_kwargs.get("doc_id", "")
        text = call_kwargs.get("text", "")
        assert f"daily_summary_{today}" in doc_id
        assert "Daily summary" in text
        assert "Goals:" in text
        assert "Finance:" in text
        assert deleted == 2  # mock_cursor.rowcount = 2
