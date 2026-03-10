"""LLM Router — умный выбор модели для каждой задачи.

Целевые роли моделей:
  routine   → Gemini 2.5 Flash Lite (бесплатный, чат/рутина/классификация)
  content   → Claude Sonnet 4.6 (качественные коммерческие тексты/карточки товаров)
  code      → OpenAI o3 (кодинг, рефакторинг, сложные правки)
  self_heal → OpenAI o3 (самолечение/исправления), далее fallback
  research  → Perplexity Sonar Pro (исследования с источниками)
  strategy  → Claude Opus 4.6 (стратегия), а мультиролевой brainstorm — через JudgeProtocol

Прямые API предпочтительнее. OpenRouter — только как fallback.
"""

import asyncio
import sqlite3
import time
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

import anthropic
import openai
from openai import AsyncOpenAI

from config.logger import get_logger
from config.settings import settings
from modules.llm_guardrails import LLMGuardrails
from modules.research_url_context import ResearchURLContextPipeline

logger = get_logger("llm_router", agent="llm_router")

# Sentinel: no financial controller attached yet
_NO_FINANCE = object()


class TaskType(Enum):
    CONTENT = "content"
    STRATEGY = "strategy"
    CODE = "code"
    RESEARCH = "research"
    ROUTINE = "routine"
    SELF_HEAL = "self_heal"


@dataclass
class ModelConfig:
    provider: str          # anthropic / openai / google / perplexity / openrouter
    model_id: str          # ID модели для API
    display_name: str
    cost_per_1k_input: float   # USD за 1K input tokens
    cost_per_1k_output: float  # USD за 1K output tokens
    max_tokens: int


# Таблица моделей — обновляется knowledge_updater.py каждый понедельник
MODEL_REGISTRY: dict[str, ModelConfig] = {
    # -- Бесплатный / рутинный уровень --
    "gemini-flash": ModelConfig(
        provider="google",
        model_id=str(getattr(settings, "LLM_FORCE_GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"),
        display_name="Gemini 2.5 Flash",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        max_tokens=8192,
    ),
    # -- Умеренный уровень (дёшево, но умнее) --
    "claude-haiku": ModelConfig(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.004,
        max_tokens=8192,
    ),
    "gpt-4o-mini": ModelConfig(
        provider="openai",
        model_id="gpt-4o-mini",
        display_name="GPT-4o Mini",
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
        max_tokens=4096,
    ),
    # -- Качественный контент --
    "claude-sonnet": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        max_tokens=8192,
    ),
    # -- Код / self-healing (Codex) --
    "gpt-o3": ModelConfig(
        provider="openai",
        model_id="o3",
        display_name="OpenAI o3",
        cost_per_1k_input=0.010,
        cost_per_1k_output=0.040,
        max_tokens=4096,
    ),
    # -- Strategy brainstorm --
    "gpt-5": ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o Strategic Alias",
        cost_per_1k_input=0.0025,
        cost_per_1k_output=0.010,
        max_tokens=4096,
    ),
    # -- Стратегия + большие изменения --
    "claude-opus": ModelConfig(
        provider="anthropic",
        model_id="claude-opus-4-6",
        display_name="Claude Opus 4.6",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        max_tokens=4096,
    ),
    # -- Исследования --
    "perplexity": ModelConfig(
        provider="perplexity",
        model_id="sonar-pro",
        display_name="Perplexity Sonar Pro",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        max_tokens=4096,
    ),
}

# Маппинг: тип задачи → приоритетный список моделей (первая = default, остальные = fallback)
# Важно: для коммерческих текстов first = Sonnet, для кода/self-heal first = o3.
TASK_MODEL_MAP: dict[TaskType, list[str]] = {
    TaskType.ROUTINE: ["gemini-flash", "gpt-4o-mini", "claude-haiku"],
    TaskType.CONTENT: ["claude-sonnet", "claude-haiku", "gemini-flash"],
    TaskType.CODE: ["gpt-o3", "claude-sonnet", "gpt-5", "gemini-flash"],
    TaskType.RESEARCH: ["perplexity", "gemini-flash", "claude-sonnet"],
    TaskType.STRATEGY: ["claude-opus", "gpt-5", "claude-sonnet", "gemini-flash"],
    TaskType.SELF_HEAL: ["gpt-o3", "claude-sonnet", "gpt-5", "gemini-flash"],
}


@dataclass
class RouteResult:
    model: ModelConfig
    task_type: TaskType
    estimated_cost_usd: float
    reasoning: str
    needs_approval: bool  # True если стоимость > $1.00


class LLMRouter:
    def __init__(self, sqlite_path: str | None = None, finance=None, comms=None):
        self._anthropic: anthropic.AsyncAnthropic | None = None
        self._openai: AsyncOpenAI | None = None
        self._google: Any | None = None
        self._openrouter: AsyncOpenAI | None = None
        self._gemini_calls: list[float] = []  # timestamps for rate limiting
        self._gemini_lock = asyncio.Lock()
        self._sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._sqlite_conn: sqlite3.Connection | None = None
        self._finance = finance  # FinancialController — set via set_finance()
        self._comms = comms
        self._guardrails = LLMGuardrails(sqlite_path=self._sqlite_path)
        self._research_url_context = ResearchURLContextPipeline()
        self._provider_cooldown_until: dict[str, float] = {}
        self._init_spend_table()
        logger.info("LLMRouter инициализирован", extra={"event": "init"})

    def set_finance(self, finance) -> None:
        """Attach FinancialController for budget enforcement."""
        self._finance = finance

    def set_comms(self, comms) -> None:
        """Attach CommsAgent for approval dialogs."""
        self._comms = comms

    async def _gemini_rate_limit(self, max_rpm: int | None = None) -> None:
        """Enforce Gemini free tier rate limit (15 req/min)."""
        if max_rpm is None:
            max_rpm = max(1, int(getattr(settings, "GEMINI_FREE_MAX_RPM", 15) or 15))
        async with self._gemini_lock:
            now = time.monotonic()
            # Remove calls older than 60 seconds
            self._gemini_calls = [t for t in self._gemini_calls if now - t < 60]
            if len(self._gemini_calls) >= max_rpm:
                wait = 60 - (now - self._gemini_calls[0])
                if wait > 0:
                    logger.info(f"Gemini rate limit: ждём {wait:.1f}s", extra={"event": "gemini_rate_wait"})
                    await asyncio.sleep(wait)
            self._gemini_calls.append(time.monotonic())

    def _get_sqlite(self) -> sqlite3.Connection:
        if self._sqlite_conn is None:
            self._sqlite_conn = sqlite3.connect(self._sqlite_path)
            self._sqlite_conn.row_factory = sqlite3.Row
        return self._sqlite_conn

    def _init_spend_table(self) -> None:
        conn = self._get_sqlite()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spend_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                model TEXT NOT NULL,
                task_type TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_spend_log_date ON spend_log(date)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_hash TEXT UNIQUE NOT NULL,
                task_type TEXT NOT NULL,
                model TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                hit_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_cache_created ON llm_cache(created_at)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gemini_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                capability TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gemini_usage_date_cap
            ON gemini_usage_log(date, capability)
        """)
        conn.commit()

    def _gemini_usage_count_today(self, capability: str) -> int:
        conn = self._get_sqlite()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM gemini_usage_log WHERE date = ? AND capability = ?",
            (date.today().isoformat(), str(capability)),
        ).fetchone()
        return int((row["n"] if row and "n" in row.keys() else 0) or 0)

    def _gemini_usage_mark(self, capability: str) -> None:
        conn = self._get_sqlite()
        conn.execute(
            "INSERT INTO gemini_usage_log (date, capability) VALUES (?, ?)",
            (date.today().isoformat(), str(capability)),
        )
        conn.commit()

    def _gemini_capability_allowed(self, capability: str, rpd_limit: int) -> bool:
        if rpd_limit <= 0:
            return True
        used = self._gemini_usage_count_today(capability)
        return used < rpd_limit

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        raw = str(text or "")
        return re.findall(r"https?://[^\s<>\"]+", raw)

    def _record_spend(self, model_name: str, task_type: str,
                      input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        conn = self._get_sqlite()
        conn.execute(
            """INSERT INTO spend_log (date, model, task_type, input_tokens, output_tokens, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (date.today().isoformat(), model_name, task_type, input_tokens, output_tokens, cost_usd),
        )
        conn.commit()
        try:
            from modules.data_lake import DataLake
            dl = DataLake()
            dl.record(
                agent="llm_router",
                task_type=f"llm:{task_type}",
                status="success",
                output={"model": model_name, "input_tokens": input_tokens, "output_tokens": output_tokens},
                cost_usd=float(cost_usd or 0.0),
                source="llm_router._record_spend",
            )
            if float(cost_usd or 0.0) > 0:
                dl.record_budget(
                    agent=f"llm_{task_type}",
                    amount=float(cost_usd),
                    category="llm",
                    description=f"model={model_name}",
                )
        except Exception:
            pass

    @property
    def anthropic_client(self) -> anthropic.AsyncAnthropic:
        if self._anthropic is None:
            self._anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic

    @property
    def openai_client(self) -> AsyncOpenAI:
        if self._openai is None:
            self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai

    @property
    def openrouter_client(self) -> AsyncOpenAI:
        if self._openrouter is None:
            self._openrouter = AsyncOpenAI(
                api_key=settings.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
            )
        return self._openrouter

    def _provider_available(self, provider: str) -> bool:
        cool_until = float(self._provider_cooldown_until.get(provider, 0.0) or 0.0)
        if cool_until > time.time():
            return False
        if provider == "anthropic":
            return bool(settings.ANTHROPIC_API_KEY)
        if provider == "openai":
            return bool(settings.OPENAI_API_KEY)
        if provider == "google":
            return bool(settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY)
        if provider == "perplexity":
            return bool(settings.PERPLEXITY_API_KEY)
        if provider == "openrouter":
            return bool(settings.OPENROUTER_API_KEY)
        return False

    def _provider_backoff_seconds(self, error_str: str) -> float:
        low = str(error_str or "").lower()
        # Auth/invalid key: aggressive cooldown to stop token waste.
        if any(m in low for m in ("invalid x-api-key", "authentication_error", "unauthorized", "error code: 401", "\"status\": 401")):
            return 15 * 60
        # Quota/rate-limit: shorter cooldown.
        if any(m in low for m in ("insufficient_quota", "resource_exhausted", "rate_limit", "quota")):
            m = re.search(r"retry in\\s+([0-9]+(?:\\.[0-9]+)?)s", low)
            if m:
                try:
                    return max(30.0, min(15 * 60.0, float(m.group(1))))
                except Exception:
                    pass
            m2 = re.search(r"retrydelay['\"]?\\s*[:=]\\s*['\"]?([0-9]+)s", low)
            if m2:
                try:
                    return max(30.0, min(15 * 60.0, float(m2.group(1))))
                except Exception:
                    pass
            return 5 * 60
        return 0.0

    def _openrouter_model_id(self, model: ModelConfig) -> str:
        # Optional override mapping via env JSON: {"claude-opus-4-6":"anthropic/claude-3.7-sonnet"}
        try:
            raw = os.getenv("OPENROUTER_MODEL_MAP", "")
            if raw:
                import json
                mp = json.loads(raw)
                if isinstance(mp, dict) and model.model_id in mp:
                    return str(mp[model.model_id])
        except Exception:
            pass
        return settings.OPENROUTER_DEFAULT_MODEL or "openai/gpt-4o-mini"

    def _model_allowed(self, model: ModelConfig) -> bool:
        enabled = {x.strip() for x in (settings.LLM_ENABLED_MODELS or "").split(",") if x.strip()}
        disabled = {x.strip() for x in (settings.LLM_DISABLED_MODELS or "").split(",") if x.strip()}
        if enabled:
            return model.model_id in enabled or model.display_name in enabled
        if disabled:
            return not (model.model_id in disabled or model.display_name in disabled)
        return True

    def _candidate_model_keys(self, task_type: TaskType) -> list[str]:
        # Sync Gemini model id dynamically (mode can change at runtime via Telegram).
        MODEL_REGISTRY["gemini-flash"].model_id = str(
            getattr(settings, "LLM_FORCE_GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
        )
        # Temporary cost-safe mode: force all tasks through free Gemini 2.5 Flash Lite.
        if bool(getattr(settings, "LLM_FORCE_GEMINI_FREE", False)):
            return ["gemini-flash"]

        keys = list(TASK_MODEL_MAP[task_type])
        allowed = [k for k in keys if self._model_allowed(MODEL_REGISTRY[k])]
        if allowed:
            return allowed
        # If allowlist/denylist accidentally blocks all candidates, prefer free Gemini fallback.
        return ["gemini-flash"]

    def get_research_route_plan(self) -> dict[str, Any]:
        """Return explicit research-stage router plan without forcing live activation.

        This formalizes the desired future split:
        - raw_research
        - synthesis
        - judge
        while keeping current single-call TaskType.RESEARCH behavior intact.
        """
        mode = str(getattr(settings, "RESEARCH_ROUTER_MODE", "test") or "test").strip().lower()
        force_free = bool(getattr(settings, "LLM_FORCE_GEMINI_FREE", False))
        if force_free or mode in {"test", "gemini", "gemini_only", "gemini-test"}:
            return {
                "mode": "gemini_test",
                "active_for_single_call": "gemini-flash",
                "raw_research": {"model_key": "gemini-flash", "role": "collect and summarize evidence cheaply"},
                "synthesis": {"model_key": "gemini-flash", "role": "build ranked operator report"},
                "judge": {"model_key": "gemini-flash", "role": "final quality/risk pass"},
            }
        return {
            "mode": "battle",
            "active_for_single_call": "perplexity",
            "raw_research": {"model_key": "perplexity", "role": "web-grounded evidence collection"},
            "synthesis": {"model_key": "claude-sonnet", "role": "turn evidence into structured monetization report"},
            "judge": {"model_key": "gpt-5", "role": "second-opinion quality/risk decision"},
            "fallbacks": {
                "raw_research": ["gemini-flash"],
                "synthesis": ["gpt-5", "gemini-flash"],
                "judge": ["claude-opus", "gemini-flash"],
            },
        }

    def select_model(
        self, task_type: TaskType, estimated_tokens: int = 2000, context: str = ""
    ) -> RouteResult:
        """Выбирает оптимальную модель для задачи."""
        model_keys = self._candidate_model_keys(task_type)
        model = MODEL_REGISTRY[model_keys[0]]

        estimated_cost = (
            (estimated_tokens / 1000) * model.cost_per_1k_input
            + (estimated_tokens / 1000) * model.cost_per_1k_output
        )

        needs_approval = estimated_cost > 1.00

        reasoning = (
            f"Задача [{task_type.value}] → {model.display_name} "
            f"(~${estimated_cost:.3f}). "
            f"{'Требуется одобрение владельца.' if needs_approval else 'В пределах автолимита.'}"
        )

        logger.info(
            reasoning,
            extra={
                "event": "model_selected",
                "context": {
                    "task_type": task_type.value,
                    "model": model.display_name,
                    "estimated_cost": estimated_cost,
                    "needs_approval": needs_approval,
                },
            },
        )
        try:
            from modules.data_lake import DataLake
            DataLake().record_decision(
                actor="llm_router",
                decision=f"model:{model.display_name} task:{task_type.value}",
                rationale=reasoning,
            )
        except Exception:
            pass

        return RouteResult(
            model=model,
            task_type=task_type,
            estimated_cost_usd=estimated_cost,
            reasoning=reasoning,
            needs_approval=needs_approval,
        )

    async def call_llm(
        self,
        task_type: TaskType,
        prompt: str,
        system_prompt: str = "",
        estimated_tokens: int = 2000,
    ) -> Optional[str]:
        """Вызывает LLM с автоматическим выбором модели и fallback."""
        if getattr(settings, "GUARDRAILS_ENABLED", True):
            try:
                guard = self._guardrails.inspect_prompt(task_type=task_type.value, prompt=prompt or "")
                if guard.get("blocked"):
                    logger.warning(
                        f"LLM call blocked by guardrails: {guard.get('reason')}",
                        extra={"event": "guardrails_block"},
                    )
                    try:
                        from modules.data_lake import DataLake
                        DataLake().record(
                            agent="llm_router",
                            task_type=f"llm:{task_type.value}",
                            status="blocked",
                            output={"reason": guard.get("reason", "guardrails")},
                            severity="warning",
                            source="llm_guardrails",
                        )
                    except Exception:
                        pass
                    return None
            except Exception:
                pass

        prompt_to_use = prompt
        source_trace = []
        if task_type == TaskType.RESEARCH and bool(getattr(settings, "RESEARCH_URL_CONTEXT_ENABLED", True)):
            try:
                prompt_to_use, source_trace = await self._research_url_context.enrich_prompt(prompt)
            except Exception as e:
                logger.debug(f"Research URL-context skipped: {e}")

        route = self.select_model(task_type, estimated_tokens)
        model = route.model
        cached = self._cache_get(task_type, model, prompt_to_use, system_prompt)
        if cached is not None:
            logger.info(
                f"LLM cache hit: {model.display_name}",
                extra={"event": "llm_cache_hit", "context": {"model": model.display_name, "task_type": task_type.value}},
            )
            return self._research_url_context.append_sources(cached, source_trace) if source_trace else cached

        # ── Budget enforcement: блокируем если лимит исчерпан ──
        if not self.check_daily_limit():
            logger.warning(
                "call_llm заблокирован: дневной лимит исчерпан",
                extra={"event": "call_blocked_budget"},
            )
            return None

        # Проверка через FinancialController (если подключён)
        if self._finance and route.estimated_cost_usd > 0:
            budget_check = self._finance.check_expense(route.estimated_cost_usd)
            if not budget_check["allowed"]:
                logger.warning(
                    f"call_llm заблокирован финконтроллером: {budget_check['reason']}",
                    extra={"event": "call_blocked_finance", "context": budget_check},
                )
                return None

        if route.needs_approval:
            logger.warning(
                f"Операция требует одобрения: ${route.estimated_cost_usd:.2f}",
                extra={"event": "approval_required"},
            )
            if self._comms:
                try:
                    # Offer recommended model + cheaper fallback (if exists)
                    alt = None
                    try:
                        keys = self._candidate_model_keys(task_type)
                        if len(keys) > 1:
                            alt = MODEL_REGISTRY[keys[1]]
                    except Exception:
                        alt = None
                    msg = (
                        "🤖 Запрос на выбор модели\n"
                        f"Задача: {task_type.value}\n"
                        f"Рекомендую: {model.display_name}\n"
                        f"Оценка стоимости: ${route.estimated_cost_usd:.2f}\n"
                    )
                    if alt:
                        msg += f"Альтернатива: {alt.display_name}\n"
                    msg += "Подтвердить запуск рекомендованной модели? ✅/❌"
                    approved = await self._comms.request_approval(
                        request_id=f"llm_model_{int(time.time())}",
                        message=msg,
                        timeout_seconds=3600,
                    )
                    if approved is not True:
                        return None
                except Exception:
                    return None
            else:
                return None

        start = time.monotonic()
        model_keys = self._candidate_model_keys(task_type)

        retry_delays = [5, 15, 30]  # exponential backoff for 529/overloaded
        # Backward-compatible context passing for provider layer (tests can still mock 3-arg _call_provider).
        self._provider_task_type_ctx = task_type

        for attempt, key in enumerate(model_keys):
            model = MODEL_REGISTRY[key]
            for retry in range(len(retry_delays) + 1):
                try:
                    # Fallback to OpenRouter if direct provider not available.
                    # In forced free-Gemini mode we do not fallback to paid providers.
                    force_free = bool(getattr(settings, "LLM_FORCE_GEMINI_FREE", False))
                    if force_free and not self._provider_available(model.provider):
                        logger.warning(
                            "Free Gemini mode enabled and Gemini key unavailable; LLM call skipped.",
                            extra={"event": "llm_free_mode_no_provider"},
                        )
                        return None
                    if not self._provider_available(model.provider) and self._provider_available("openrouter"):
                        or_model = ModelConfig(
                            provider="openrouter",
                            model_id=self._openrouter_model_id(model),
                            display_name=f"OpenRouter({model.display_name})",
                            cost_per_1k_input=model.cost_per_1k_input,
                            cost_per_1k_output=model.cost_per_1k_output,
                            max_tokens=model.max_tokens,
                        )
                        text, real_cost = await self._call_provider(or_model, prompt_to_use, system_prompt)
                        model = or_model
                    else:
                        text, real_cost = await self._call_provider(model, prompt_to_use, system_prompt)
                    duration_ms = int((time.monotonic() - start) * 1000)
                    self._record_spend(
                        model_name=model.display_name,
                        task_type=task_type.value,
                        input_tokens=0,
                        output_tokens=0,
                        cost_usd=real_cost,
                    )

                    # Bridge: record in FinancialController for unified P&L
                    if self._finance and real_cost > 0:
                        try:
                            from financial_controller import ExpenseCategory
                            self._finance.record_expense(
                                amount_usd=real_cost,
                                category=ExpenseCategory.API,
                                agent=f"llm_{task_type.value}",
                                description=f"{model.display_name}: {task_type.value}",
                            )
                        except Exception:
                            pass

                    logger.info(
                        f"LLM ответ получен от {model.display_name}",
                        extra={
                            "event": "llm_call_success",
                            "duration_ms": duration_ms,
                            "context": {
                                "model": model.display_name,
                                "attempt": attempt + 1,
                                "retry": retry,
                                "real_cost": real_cost,
                                "daily_spend": self.get_daily_spend(),
                            },
                        },
                    )
                    self._cache_set(task_type, model, prompt_to_use, system_prompt, text)
                    return self._research_url_context.append_sources(text, source_trace) if source_trace else text

                except Exception as e:
                    error_str = str(e)
                    backoff = self._provider_backoff_seconds(error_str)
                    if backoff > 0:
                        self._provider_cooldown_until[model.provider] = time.time() + backoff
                        logger.warning(
                            f"Provider cooldown set: {model.provider} for {int(backoff)}s",
                            extra={"event": "provider_cooldown_set", "context": {"provider": model.provider, "seconds": int(backoff)}},
                        )
                    # Try OpenRouter fallback once on auth/network errors
                    if self._provider_available("openrouter") and model.provider != "openrouter":
                        try:
                            or_model = ModelConfig(
                                provider="openrouter",
                                model_id=self._openrouter_model_id(model),
                                display_name=f"OpenRouter({model.display_name})",
                                cost_per_1k_input=model.cost_per_1k_input,
                                cost_per_1k_output=model.cost_per_1k_output,
                                max_tokens=model.max_tokens,
                            )
                            text, real_cost = await self._call_provider(or_model, prompt_to_use, system_prompt)
                            duration_ms = int((time.monotonic() - start) * 1000)
                            self._record_spend(
                                model_name=or_model.display_name,
                                task_type=task_type.value,
                                input_tokens=0,
                                output_tokens=0,
                                cost_usd=real_cost,
                            )
                            if self._finance and real_cost > 0:
                                try:
                                    from financial_controller import ExpenseCategory
                                    self._finance.record_expense(
                                        amount_usd=real_cost,
                                        category=ExpenseCategory.API,
                                        agent=f"llm_{task_type.value}",
                                        description=f"{or_model.display_name}: {task_type.value}",
                                    )
                                except Exception:
                                    pass
                            logger.info(
                                f"LLM ответ получен от {or_model.display_name}",
                                extra={
                                    "event": "llm_call_success",
                                    "duration_ms": duration_ms,
                                    "context": {
                                        "model": or_model.display_name,
                                        "attempt": attempt + 1,
                                        "retry": retry,
                                        "real_cost": real_cost,
                                        "daily_spend": self.get_daily_spend(),
                                    },
                                },
                            )
                            self._cache_set(task_type, or_model, prompt_to_use, system_prompt, text)
                            return self._research_url_context.append_sources(text, source_trace) if source_trace else text
                        except Exception:
                            pass
                    # Retry on 529 (overloaded) and 500 (server error)
                    is_retryable = any(code in error_str for code in ("529", "overloaded", "500", "503", "rate_limit"))
                    if is_retryable and retry < len(retry_delays):
                        delay = retry_delays[retry]
                        logger.warning(
                            f"{model.display_name} overloaded, retry {retry + 1} in {delay}s",
                            extra={"event": "llm_retry", "context": {"delay": delay}},
                        )
                        await asyncio.sleep(delay)
                        continue

                    logger.error(
                        f"Ошибка вызова {model.display_name}: {e}",
                        extra={
                            "event": "llm_call_failed",
                            "context": {"model": model.display_name, "attempt": attempt + 1},
                        },
                        exc_info=True,
                    )
                    break  # move to next model

        logger.critical(
            "Все модели недоступны для задачи",
            extra={"event": "all_models_failed"},
        )
        return None
        
        

    def _cache_key(self, task_type: TaskType, model: ModelConfig, prompt: str, system_prompt: str) -> str:
        raw = f"{task_type.value}|{model.model_id}|{system_prompt}|{prompt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_ttl_seconds(self, task_type: TaskType) -> int:
        if task_type not in (TaskType.ROUTINE, TaskType.CONTENT):
            return 0
        ttl_hours = max(int(getattr(settings, "LLM_CACHE_TTL_HOURS", 0)), 0)
        return ttl_hours * 3600

    def _cache_get(self, task_type: TaskType, model: ModelConfig, prompt: str, system_prompt: str) -> Optional[str]:
        ttl = self._cache_ttl_seconds(task_type)
        if ttl <= 0:
            return None
        key = self._cache_key(task_type, model, prompt, system_prompt)
        conn = self._get_sqlite()
        row = conn.execute(
            "SELECT response, created_at, hit_count FROM llm_cache WHERE prompt_hash = ?",
            (key,),
        ).fetchone()
        if not row:
            return None
        try:
            created = datetime.fromisoformat(row["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except Exception:
            created = datetime.now(timezone.utc)
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > ttl:
            conn.execute("DELETE FROM llm_cache WHERE prompt_hash = ?", (key,))
            conn.commit()
            return None
        try:
            conn.execute(
                "UPDATE llm_cache SET hit_count = hit_count + 1 WHERE prompt_hash = ?",
                (key,),
            )
            conn.commit()
        except Exception:
            pass
        return row["response"]

    def _cache_set(self, task_type: TaskType, model: ModelConfig, prompt: str, system_prompt: str, response: str) -> None:
        ttl = self._cache_ttl_seconds(task_type)
        if ttl <= 0:
            return
        key = self._cache_key(task_type, model, prompt, system_prompt)
        conn = self._get_sqlite()
        try:
            conn.execute(
                """INSERT INTO llm_cache (prompt_hash, task_type, model, response, created_at, hit_count)
                   VALUES (?, ?, ?, ?, datetime('now'), 0)
                   ON CONFLICT(prompt_hash) DO UPDATE SET
                     response = excluded.response,
                     created_at = datetime('now'),
                     hit_count = 0""",
                (key, task_type.value, model.display_name, response),
            )
            conn.commit()
        except Exception:
            pass

    def _calc_cost(self, model: ModelConfig, input_tokens: int, output_tokens: int) -> float:
        """Считает реальную стоимость по usage из ответа API."""
        return (
            (input_tokens / 1000) * model.cost_per_1k_input
            + (output_tokens / 1000) * model.cost_per_1k_output
        )

    async def _call_provider(
        self, model: ModelConfig, prompt: str, system_prompt: str, task_type: TaskType | None = None
    ) -> tuple[str, float]:
        """Вызов конкретного провайдера. Возвращает (text, real_cost_usd)."""
        if task_type is None:
            task_type = getattr(self, "_provider_task_type_ctx", None)
        if model.provider == "anthropic":
            response = await asyncio.wait_for(
                self.anthropic_client.messages.create(
                    model=model.model_id,
                    max_tokens=model.max_tokens,
                    system=system_prompt or "You are VITO, an autonomous AI agent.",
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=60,
            )
            cost = self._calc_cost(
                model, response.usage.input_tokens, response.usage.output_tokens
            )
            return response.content[0].text, cost

        elif model.provider == "openai":
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await asyncio.wait_for(
                self.openai_client.chat.completions.create(
                    model=model.model_id,
                    messages=messages,
                    max_completion_tokens=model.max_tokens,
                ),
                timeout=60,
            )
            cost = 0.0
            if response.usage:
                cost = self._calc_cost(
                    model, response.usage.prompt_tokens, response.usage.completion_tokens
                )
            return response.choices[0].message.content, cost

        elif model.provider == "google":
            if self._google is None:
                try:
                    from google import genai
                except ImportError:
                    raise RuntimeError("google-genai не установлен, Gemini недоступен")
                # Prefer GEMINI_API_KEY (AI Studio) over GOOGLE_API_KEY (Custom Search)
                gemini_key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
                self._google = genai.Client(api_key=gemini_key)
            text_rpd = max(1, int(getattr(settings, "GEMINI_FREE_TEXT_RPD", 1000) or 1000))
            if not self._gemini_capability_allowed("text", text_rpd):
                raise RuntimeError("gemini_text_daily_limit_reached")
            contents = prompt
            if system_prompt:
                contents = f"{system_prompt}\n\n{prompt}"
            # Rate limit: Gemini free tier = 15 req/min
            await self._gemini_rate_limit()
            gen_kwargs: dict[str, Any] = {"model": model.model_id, "contents": contents}
            enable_search = bool(getattr(settings, "GEMINI_ENABLE_GROUNDING_SEARCH", True))
            enable_url_ctx = bool(getattr(settings, "GEMINI_ENABLE_URL_CONTEXT", True))
            urls = self._extract_urls(prompt) if enable_url_ctx else []
            should_ground = bool(enable_search and task_type == TaskType.RESEARCH)
            search_rpd = max(1, int(getattr(settings, "GEMINI_FREE_SEARCH_RPD", 1500) or 1500))
            used_search = False
            if should_ground and self._gemini_capability_allowed("grounding_search", search_rpd):
                try:
                    # google-genai >= 0.7 style config
                    from google.genai import types as genai_types  # type: ignore

                    gen_kwargs["config"] = genai_types.GenerateContentConfig(
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                    )
                    used_search = True
                except Exception:
                    # Safe fallback: plain generation without hard failure.
                    used_search = False
            if urls:
                # URL-context mode: explicit directive for model to read referenced pages directly.
                url_hint = (
                    "Если в запросе есть URL, прочитай их содержимое и используй как первоисточник. "
                    "Если URL недоступен — явно укажи это в ответе."
                )
                if "config" in gen_kwargs:
                    # Keep configured tools and reinforce behavior in contents.
                    gen_kwargs["contents"] = f"{contents}\n\n{url_hint}"
                else:
                    gen_kwargs["contents"] = f"{contents}\n\n{url_hint}"
            response = self._google.models.generate_content(**gen_kwargs)
            self._gemini_usage_mark("text")
            if used_search:
                self._gemini_usage_mark("grounding_search")
            # Gemini free tier — cost = 0
            cost = 0.0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                cost = self._calc_cost(
                    model,
                    getattr(um, "prompt_token_count", 0),
                    getattr(um, "candidates_token_count", 0),
                )
            return response.text, cost

        elif model.provider == "perplexity":
            if not hasattr(self, "_perplexity") or self._perplexity is None:
                self._perplexity = AsyncOpenAI(
                    api_key=settings.PERPLEXITY_API_KEY,
                    base_url="https://api.perplexity.ai",
                )
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await asyncio.wait_for(
                self._perplexity.chat.completions.create(
                    model=model.model_id,
                    messages=messages,
                ),
                timeout=45,
            )
            cost = 0.0
            if response.usage:
                cost = self._calc_cost(
                    model, response.usage.prompt_tokens, response.usage.completion_tokens
                )
            return response.choices[0].message.content, cost
        elif model.provider == "openrouter":
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await asyncio.wait_for(
                self.openrouter_client.chat.completions.create(
                    model=model.model_id,
                    messages=messages,
                    max_completion_tokens=model.max_tokens,
                ),
                timeout=60,
            )
            cost = 0.0
            if response.usage:
                cost = self._calc_cost(
                    model, response.usage.prompt_tokens, response.usage.completion_tokens
                )
            return response.choices[0].message.content, cost

        else:
            raise ValueError(f"Неизвестный провайдер: {model.provider}")

    def get_daily_spend(self) -> float:
        """Читает сумму расходов за сегодня из SQLite."""
        conn = self._get_sqlite()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM spend_log WHERE date = ?",
            (date.today().isoformat(),),
        ).fetchone()
        return float(row["total"])

    def get_spend_breakdown(self, days: int = 1) -> list[dict]:
        """Разбивка расходов по моделям за N дней."""
        conn = self._get_sqlite()
        rows = conn.execute(
            """SELECT model, task_type, COUNT(*) as calls,
                      SUM(cost_usd) as total_cost,
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output
               FROM spend_log
               WHERE date >= date('now', ?)
               GROUP BY model, task_type
               ORDER BY total_cost DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_spend_log_recent(self, limit: int = 20) -> list[dict]:
        """Последние N записей из spend_log (для детальной отладки)."""
        conn = self._get_sqlite()
        rows = conn.execute(
            """SELECT date, model, task_type, input_tokens, output_tokens,
                      cost_usd, created_at
               FROM spend_log ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def check_daily_limit(self) -> bool:
        """Проверяет не превышен ли дневной лимит."""
        daily_spend = self.get_daily_spend()
        if daily_spend >= settings.DAILY_LIMIT_USD:
            logger.warning(
                f"Дневной лимит достигнут: ${daily_spend:.2f}/${settings.DAILY_LIMIT_USD}",
                extra={"event": "daily_limit_reached"},
            )
            return False
        return True

    def get_policy_report(self, days: int = 1) -> dict:
        """Policy-oriented spend report for dashboard and audits."""
        rows = self.get_spend_breakdown(days=days)
        model_cfg = {k: v for k, v in MODEL_REGISTRY.items()}
        total_cost = sum(float(r.get("total_cost", 0) or 0) for r in rows)
        free_calls = 0
        paid_calls = 0
        by_provider: dict[str, dict] = {}
        for r in rows:
            model = str(r.get("model", ""))
            calls = int(r.get("calls", 0) or 0)
            cost = float(r.get("total_cost", 0) or 0)
            cfg = model_cfg.get(model)
            provider = getattr(cfg, "provider", "unknown")
            is_free = bool(cfg and cfg.cost_per_1k_input == 0 and cfg.cost_per_1k_output == 0)
            if is_free:
                free_calls += calls
            else:
                paid_calls += calls
            if provider not in by_provider:
                by_provider[provider] = {"calls": 0, "cost_usd": 0.0}
            by_provider[provider]["calls"] += calls
            by_provider[provider]["cost_usd"] += cost
        return {
            "window_days": int(days),
            "daily_limit_usd": float(settings.DAILY_LIMIT_USD),
            "daily_spend_usd": float(self.get_daily_spend()),
            "total_cost_usd": round(total_cost, 6),
            "free_calls": int(free_calls),
            "paid_calls": int(paid_calls),
            "providers": by_provider,
            "top": rows[:15],
        }
