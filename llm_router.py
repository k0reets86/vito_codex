"""LLM Router — умный выбор модели для каждой задачи.

Маппинг типов задач на оптимальные модели:
  content  → Claude Sonnet (лучшее качество/цена для текста)
  strategy → Claude Opus (глубокий анализ)
  code     → o3 / OpenAI Codex
  research → Claude Sonnet + Perplexity API
  routine  → Claude Haiku (дёшево и быстро)

Прямые API предпочтительнее. OpenRouter — только как fallback.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import anthropic
import openai

from config.logger import get_logger
from config.settings import settings

logger = get_logger("llm_router", agent="llm_router")


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
}

# Маппинг: тип задачи → основная модель (+ fallback)
TASK_MODEL_MAP: dict[TaskType, list[str]] = {
    TaskType.CONTENT: ["claude-sonnet", "claude-haiku"],
    TaskType.STRATEGY: ["claude-opus", "claude-sonnet"],
    TaskType.CODE: ["gpt-o3", "claude-sonnet"],
    TaskType.RESEARCH: ["perplexity", "claude-sonnet"],
    TaskType.ROUTINE: ["claude-haiku", "claude-sonnet"],
}


@dataclass
class RouteResult:
    model: ModelConfig
    task_type: TaskType
    estimated_cost_usd: float
    reasoning: str
    needs_approval: bool  # True если стоимость > $1.00


class LLMRouter:
    def __init__(self):
        self._anthropic = None
        self._openai = None
        self._daily_spend: float = 0.0
        logger.info("LLMRouter инициализирован", extra={"event": "init"})

    @property
    def anthropic_client(self) -> anthropic.Anthropic:
        if self._anthropic is None:
            self._anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic

    @property
    def openai_client(self) -> openai.OpenAI:
        if self._openai is None:
            self._openai = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
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
        route = self.select_model(task_type, estimated_tokens)
        model = route.model

        if route.needs_approval:
            logger.warning(
                f"Операция требует одобрения: ${route.estimated_cost_usd:.2f}",
                extra={"event": "approval_required"},
            )
            # TODO: интеграция с comms_agent для запроса одобрения через Telegram
            return None

        start = time.monotonic()
        model_keys = TASK_MODEL_MAP[task_type]

        for attempt, key in enumerate(model_keys):
            model = MODEL_REGISTRY[key]
            try:
                result = await self._call_provider(model, prompt, system_prompt)
                duration_ms = int((time.monotonic() - start) * 1000)
                self._daily_spend += route.estimated_cost_usd

                logger.info(
                    f"LLM ответ получен от {model.display_name}",
                    extra={
                        "event": "llm_call_success",
                        "duration_ms": duration_ms,
                        "context": {
                            "model": model.display_name,
                            "attempt": attempt + 1,
                            "daily_spend": self._daily_spend,
                        },
                    },
                )
                return result

            except Exception as e:
                logger.error(
                    f"Ошибка вызова {model.display_name}: {e}",
                    extra={
                        "event": "llm_call_failed",
                        "context": {"model": model.display_name, "attempt": attempt + 1},
                    },
                    exc_info=True,
                )
                continue

        logger.critical(
            "Все модели недоступны для задачи",
            extra={"event": "all_models_failed"},
        )
        return None

    async def _call_provider(
        self, model: ModelConfig, prompt: str, system_prompt: str
    ) -> str:
        """Вызов конкретного провайдера."""
        if model.provider == "anthropic":
            response = self.anthropic_client.messages.create(
                model=model.model_id,
                max_tokens=model.max_tokens,
                system=system_prompt or "You are VITO, an autonomous AI agent.",
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        elif model.provider == "openai":
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.openai_client.chat.completions.create(
                model=model.model_id,
                messages=messages,
                max_completion_tokens=model.max_tokens,
            )
            return response.choices[0].message.content

        elif model.provider == "perplexity":
            client = openai.OpenAI(
                api_key=settings.PERPLEXITY_API_KEY,
                base_url="https://api.perplexity.ai",
            )
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=model.model_id,
                messages=messages,
            )
            return response.choices[0].message.content

        else:
            raise ValueError(f"Неизвестный провайдер: {model.provider}")

    def get_daily_spend(self) -> float:
        return self._daily_spend

    def check_daily_limit(self) -> bool:
        """Проверяет не превышен ли дневной лимит."""
        if self._daily_spend >= settings.DAILY_LIMIT_USD:
            logger.warning(
                f"Дневной лимит достигнут: ${self._daily_spend:.2f}/${settings.DAILY_LIMIT_USD}",
                extra={"event": "daily_limit_reached"},
            )
            return False
        return True
