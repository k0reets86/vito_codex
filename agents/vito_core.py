"""VITOCore — Agent 00: центральный оркестратор.

Классифицирует шаги плана и диспетчеризирует к специализированным агентам.
Если подходящего агента нет — fallback на LLM через llm_router.
"""

import time
from typing import Optional

from agents.base_agent import BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("vito_core", agent="vito_core")

# Маппинг ключевых слов → capabilities
# Keyword → capability mapping.
# IMPORTANT: sorted by keyword length descending at runtime to prevent
# short substrings from matching before more specific ones.
# E.g., "цен" must not match "оценить" before "риск" or "юридическ" get a chance.
_KEYWORD_CAPABILITY_RAW = {
    # Specific multi-word/long keywords FIRST
    "unit_economics": "unit_economics",
    "юнит-экономик": "unit_economics",
    "knowledge_base": "knowledge_base",
    "key_rotation": "key_rotation",
    "конкурент": "competitor_analysis",
    "competitor": "competitor_analysis",
    "качеств": "quality_review",
    "quality": "quality_review",
    "review": "quality_review",
    "переве": "translate",  # "перевести", "перевод", "переведи"
    "translat": "translate",
    "локализ": "localize",
    "юридическ": "legal",
    "правов": "legal",
    "legal": "legal",
    "copyright": "copyright",
    "gdpr": "gdpr",
    "риск": "risk_assessment",
    "risk": "risk_assessment",
    "репутац": "reputation",
    "reput": "reputation",
    "аналитик": "analytics",
    "analytic": "analytics",
    "dashboard": "dashboard",
    "дашборд": "dashboard",
    "forecast": "forecast",
    "прогноз": "forecast",
    "безопасн": "security",
    "security": "security",
    "research": "research",
    "исследов": "research",
    "контент": "content_creation",
    "content": "content_creation",
    "article": "content_creation",
    "стать": "content_creation",
    "ebook": "ebook",
    "trend": "trend_scan",
    "тренд": "trend_scan",
    "ниш": "niche_research",
    "niche": "niche_research",
    "seo": "seo",
    "keyword": "keyword_research",
    "social": "social_media",
    "соцсет": "social_media",
    "smm": "social_media",
    "маркет": "marketing_strategy",
    "market": "marketing_strategy",
    "funnel": "funnel",
    "воронк": "funnel",
    "email": "email",
    "newsletter": "newsletter",
    "рассыл": "newsletter",
    "listing": "listing_create",
    "листинг": "listing_create",
    "ecommerce": "ecommerce",
    "магазин": "ecommerce",
    "продаж": "sales_check",
    "sales": "sales_check",
    "pricing": "pricing",
    "расцен": "pricing",
    "partner": "partnership",
    "партнёр": "partnership",
    "affiliate": "affiliate",
    "account": "account_management",
    "аккаунт": "account_management",
    "perform": "performance_evaluation",
    "произв": "performance_evaluation",
    "document": "documentation",
    "документ": "documentation",
    "отчёт": "documentation",
    "report": "documentation",
    "browse": "browse",
    "браузер": "browse",
    "scrape": "web_scrape",
    "health": "health_check",
    "здоров": "health_check",
    "backup": "backup",
    "бэкап": "backup",
    "publish": "publish",
    "публик": "publish",
    "wordpress": "wordpress",
    "hr": "hr",
}

# Sort by keyword length descending → longer (more specific) matches first
KEYWORD_CAPABILITY_MAP = dict(
    sorted(_KEYWORD_CAPABILITY_RAW.items(), key=lambda kv: len(kv[0]), reverse=True)
)


class VITOCore(BaseAgent):
    """Agent 00: центральный диспетчер задач."""

    def __init__(self, registry=None, **kwargs):
        super().__init__(
            name="vito_core",
            description="Центральный оркестратор — классифицирует и диспетчеризирует задачи",
            **kwargs,
        )
        self.registry = registry

    @property
    def capabilities(self) -> list[str]:
        return ["orchestrate", "classify", "dispatch"]

    def classify_step(self, step: str) -> Optional[str]:
        """Определяет capability для шага плана."""
        step_lower = step.lower()
        for keyword, capability in KEYWORD_CAPABILITY_MAP.items():
            if keyword in step_lower:
                return capability
        return None

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        """Классифицирует и диспетчеризирует задачу."""
        self._status_running()
        start = time.monotonic()

        step = kwargs.get("step", "")
        goal_title = kwargs.get("goal_title", "")

        # 1. Классифицируем
        capability = self.classify_step(step) if step else task_type

        # 2. Пробуем dispatch через реестр
        if capability and self.registry:
            extra_kwargs = {k: v for k, v in kwargs.items() if k not in ("step", "goal_title")}
            result = await self.registry.dispatch(capability, step=step, goal_title=goal_title, **extra_kwargs)
            if result is not None:
                duration_ms = int((time.monotonic() - start) * 1000)
                result.duration_ms = duration_ms
                self._status_idle()
                return result

        # 3. Fallback на LLM
        if self.llm_router:
            task_type_llm = self._map_to_task_type(step or task_type)
            response = await self.llm_router.call_llm(
                task_type=task_type_llm,
                prompt=f"Контекст: {goal_title}\nЗадача: {step or task_type}\nДай конкретный результат.",
                estimated_tokens=1500,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            self._status_idle()
            if response:
                return TaskResult(success=True, output=response[:500], duration_ms=duration_ms)
            return TaskResult(success=False, error="LLM не вернул ответ", duration_ms=duration_ms)

        self._status_idle()
        return TaskResult(success=False, error="Нет registry и llm_router для выполнения")

    def _map_to_task_type(self, text: str) -> TaskType:
        """Маппинг текста шага на TaskType для LLM."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["исследов", "анализ", "поиск", "research", "analyz"]):
            return TaskType.RESEARCH
        if any(w in text_lower for w in ["стратег", "план", "оцен", "strateg", "evaluat"]):
            return TaskType.STRATEGY
        if any(w in text_lower for w in ["код", "скрипт", "code", "script", "implement"]):
            return TaskType.CODE
        if any(w in text_lower for w in ["контент", "текст", "стать", "content", "write", "creat"]):
            return TaskType.CONTENT
        return TaskType.ROUTINE

    def _status_running(self):
        from agents.base_agent import AgentStatus
        self._status = AgentStatus.RUNNING

    def _status_idle(self):
        from agents.base_agent import AgentStatus
        self._status = AgentStatus.IDLE
