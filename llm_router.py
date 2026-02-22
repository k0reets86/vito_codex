"""LLM Router — умный выбор модели для каждой задачи.

Маппинг типов задач на оптимальные модели:
  content  → Claude Sonnet (лучшее качество/цена для текста)
  strategy → Claude Opus (глубокий анализ)
  code     → o3 / OpenAI Codex
  research → Claude Sonnet + Perplexity API
  routine  → Claude Haiku (дёшево и быстро)

Прямые API предпочтительнее. OpenRouter — только как fallback.
"""

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

import anthropic
import openai
from openai import AsyncOpenAI

from config.logger import get_logger
from config.settings import settings

logger = get_logger("llm_router", agent="llm_router")

# Sentinel: no financial controller attached yet
_NO_FINANCE = object()


class TaskType(Enum):
    CONTENT = "content"
    STRATEGY = "strategy"
    CODE = "code"
    RESEARCH = "research"
    ROUTINE = "routine"


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
    "claude-sonnet": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        max_tokens=8192,
    ),
    "claude-opus": ModelConfig(
        provider="anthropic",
        model_id="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        max_tokens=4096,
    ),
    "claude-haiku": ModelConfig(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.004,
        max_tokens=8192,
    ),
    "gpt-o3": ModelConfig(
        provider="openai",
        model_id="o3",
        display_name="OpenAI o3",
        cost_per_1k_input=0.010,
        cost_per_1k_output=0.040,
        max_tokens=4096,
    ),
    "perplexity": ModelConfig(
        provider="perplexity",
        model_id="sonar-pro",
        display_name="Perplexity Sonar Pro",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        max_tokens=4096,
    ),
    "gemini-flash": ModelConfig(
        provider="google",
        model_id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        max_tokens=8192,
    ),
}

# Маппинг: тип задачи → основная модель (+ fallback)
TASK_MODEL_MAP: dict[TaskType, list[str]] = {
    TaskType.CONTENT: ["claude-sonnet", "claude-haiku"],
    TaskType.STRATEGY: ["claude-opus", "claude-sonnet"],
    TaskType.CODE: ["gpt-o3", "claude-sonnet"],
    TaskType.RESEARCH: ["perplexity", "claude-sonnet"],
    TaskType.ROUTINE: ["claude-haiku", "gemini-flash"],
}


@dataclass
class RouteResult:
    model: ModelConfig
    task_type: TaskType
    estimated_cost_usd: float
    reasoning: str
    needs_approval: bool  # True если стоимость > $1.00


class LLMRouter:
    def __init__(self, sqlite_path: str | None = None, finance=None):
        self._anthropic: anthropic.AsyncAnthropic | None = None
        self._openai: AsyncOpenAI | None = None
        self._google: Any | None = None
        self._gemini_calls: list[float] = []  # timestamps for rate limiting
        self._gemini_lock = asyncio.Lock()
        self._sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._sqlite_conn: sqlite3.Connection | None = None
        self._finance = finance  # FinancialController — set via set_finance()
        self._init_spend_table()
        logger.info("LLMRouter инициализирован", extra={"event": "init"})

    def set_finance(self, finance) -> None:
        """Attach FinancialController for budget enforcement."""
        self._finance = finance

    async def _gemini_rate_limit(self, max_rpm: int = 15) -> None:
        """Enforce Gemini free tier rate limit (15 req/min)."""
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
        conn.commit()

    def _record_spend(self, model_name: str, task_type: str,
                      input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        conn = self._get_sqlite()
        conn.execute(
            """INSERT INTO spend_log (date, model, task_type, input_tokens, output_tokens, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (date.today().isoformat(), model_name, task_type, input_tokens, output_tokens, cost_usd),
        )
        conn.commit()

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

    def select_model(
        self, task_type: TaskType, estimated_tokens: int = 2000, context: str = ""
    ) -> RouteResult:
        """Выбирает оптимальную модель для задачи."""
        model_keys = TASK_MODEL_MAP[task_type]
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
        # ── Budget enforcement: блокируем если лимит исчерпан ──
        if not self.check_daily_limit():
            logger.warning(
                "call_llm заблокирован: дневной лимит исчерпан",
                extra={"event": "call_blocked_budget"},
            )
            return None

        route = self.select_model(task_type, estimated_tokens)
        model = route.model

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
            return None

        start = time.monotonic()
        model_keys = TASK_MODEL_MAP[task_type]

        retry_delays = [5, 15, 30]  # exponential backoff for 529/overloaded

        for attempt, key in enumerate(model_keys):
            model = MODEL_REGISTRY[key]
            for retry in range(len(retry_delays) + 1):
                try:
                    text, real_cost = await self._call_provider(model, prompt, system_prompt)
                    duration_ms = int((time.monotonic() - start) * 1000)
                    self._record_spend(
                        model_name=model.display_name,
                        task_type=task_type.value,
                        input_tokens=0,
                        output_tokens=0,
                        cost_usd=real_cost,
                    )

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
                    return text

                except Exception as e:
                    error_str = str(e)
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

    def _calc_cost(self, model: ModelConfig, input_tokens: int, output_tokens: int) -> float:
        """Считает реальную стоимость по usage из ответа API."""
        return (
            (input_tokens / 1000) * model.cost_per_1k_input
            + (output_tokens / 1000) * model.cost_per_1k_output
        )

    async def _call_provider(
        self, model: ModelConfig, prompt: str, system_prompt: str
    ) -> tuple[str, float]:
        """Вызов конкретного провайдера. Возвращает (text, real_cost_usd)."""
        if model.provider == "anthropic":
            response = await self.anthropic_client.messages.create(
                model=model.model_id,
                max_tokens=model.max_tokens,
                system=system_prompt or "You are VITO, an autonomous AI agent.",
                messages=[{"role": "user", "content": prompt}],
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
            response = await self.openai_client.chat.completions.create(
                model=model.model_id,
                messages=messages,
                max_completion_tokens=model.max_tokens,
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
            contents = prompt
            if system_prompt:
                contents = f"{system_prompt}\n\n{prompt}"
            # Rate limit: Gemini free tier = 15 req/min
            await self._gemini_rate_limit()
            response = self._google.models.generate_content(
                model=model.model_id,
                contents=contents,
            )
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
            response = await self._perplexity.chat.completions.create(
                model=model.model_id,
                messages=messages,
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
