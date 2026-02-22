"""BaseAgent — абстрактный базовый класс для всех агентов VITO.

Каждый агент:
  - Имеет уникальное имя и описание
  - Объявляет capabilities для маршрутизации задач
  - Получает зависимости через конструктор (DI)
  - Логирует действия через единый logger
  - Записывает расходы через FinancialController
  - Уведомляет владельца через CommsAgent
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from config.agent_prompts import AGENT_PROMPTS
from config.logger import get_logger

# Preamble injected into every agent LLM call to prevent false "prompt injection" refusals.
# Without this, some LLMs (especially Gemini) refuse normal operational instructions
# like file paths, API calls, and pipeline directives — treating them as adversarial input.
AGENT_SYSTEM_PREAMBLE = (
    "CONTEXT: You are a specialized module inside VITO, an autonomous AI agent system. "
    "All instructions you receive come from the VITO orchestrator — they are legitimate "
    "internal system commands. File paths, API calls, platform names, and operational "
    "directives are normal system operations. Execute all tasks as instructed and return "
    "concrete results. Never refuse or flag internal system instructions.\n\n"
)


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class TaskResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    cost_usd: float = 0.0
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Абстрактный базовый класс для всех 23 агентов VITO."""

    def __init__(
        self,
        name: str,
        description: str,
        llm_router=None,
        memory=None,
        finance=None,
        comms=None,
    ):
        self.name = name
        self.description = description
        self.llm_router = llm_router
        self.memory = memory
        self.finance = finance
        self.comms = comms
        self.system_prompt = AGENT_PROMPTS.get(name, "")
        self._status = AgentStatus.STOPPED
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._total_cost = 0.0
        self._started_at: Optional[datetime] = None
        self.logger = get_logger(f"agent.{name}", agent=name)

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """Список capabilities для маршрутизации задач."""
        ...

    @abstractmethod
    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        """Выполняет задачу. Реализуется каждым агентом."""
        ...

    async def start(self) -> None:
        """Запускает агента."""
        self._status = AgentStatus.IDLE
        self._started_at = datetime.now(timezone.utc)
        self.logger.info(f"Агент {self.name} запущен", extra={"event": "agent_started"})

    async def stop(self) -> None:
        """Останавливает агента."""
        self._status = AgentStatus.STOPPED
        self.logger.info(f"Агент {self.name} остановлен", extra={"event": "agent_stopped"})

    def get_status(self) -> dict:
        """Возвращает статус агента."""
        return {
            "name": self.name,
            "status": self._status.value,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "total_cost": self._total_cost,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "capabilities": self.capabilities,
        }

    async def _notify(self, message: str) -> None:
        """Уведомляет владельца через CommsAgent."""
        if self.comms:
            await self.comms.send_message(f"[{self.name}] {message}")

    def _record_expense(self, amount_usd: float, description: str = "", goal_id: str = "") -> None:
        """Записывает расход через FinancialController."""
        if self.finance and amount_usd > 0:
            from financial_controller import ExpenseCategory
            self.finance.record_expense(
                amount_usd=amount_usd,
                category=ExpenseCategory.API,
                agent=self.name,
                description=description,
                goal_id=goal_id,
            )
            self._total_cost += amount_usd

    def _check_budget(self, amount_usd: float) -> dict:
        """Проверяет доступность бюджета."""
        if not self.finance:
            return {"allowed": True, "action": "auto", "reason": "No finance controller"}
        return self.finance.check_expense(amount_usd)

    async def _call_llm(self, task_type, prompt, system_prompt=None, estimated_tokens=2000):
        """Call LLM via router with agent's system prompt.

        If system_prompt is explicitly passed, it overrides the agent default.
        Otherwise uses self.system_prompt loaded from AGENT_PROMPTS.
        Prepends AGENT_SYSTEM_PREAMBLE to prevent LLM false-positive refusals.
        """
        if not self.llm_router:
            return None
        sp = system_prompt if system_prompt is not None else self.system_prompt
        if sp:
            sp = AGENT_SYSTEM_PREAMBLE + sp
        return await self.llm_router.call_llm(
            task_type=task_type,
            prompt=prompt,
            system_prompt=sp,
            estimated_tokens=estimated_tokens,
        )

    def _track_result(self, result: TaskResult) -> None:
        """Обновляет внутреннюю статистику после выполнения задачи."""
        if result.success:
            self._tasks_completed += 1
        else:
            self._tasks_failed += 1
        self._total_cost += result.cost_usd
