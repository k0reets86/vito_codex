"""AgentRegistry — реестр и диспетчер агентов VITO.

Управляет жизненным циклом агентов:
  - Регистрация/удаление
  - Поиск по capabilities
  - Диспетчеризация задач к подходящему агенту
  - Групповой запуск/остановка
"""

from typing import Optional

from agents.base_agent import BaseAgent, TaskResult
from config.logger import get_logger

logger = get_logger("agent_registry", agent="registry")


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        logger.info("AgentRegistry инициализирован", extra={"event": "init"})

    def register(self, agent: BaseAgent) -> None:
        """Регистрирует агента в реестре."""
        self._agents[agent.name] = agent
        logger.info(
            f"Агент зарегистрирован: {agent.name} ({', '.join(agent.capabilities)})",
            extra={"event": "agent_registered", "context": {"agent": agent.name}},
        )

    def unregister(self, name: str) -> Optional[BaseAgent]:
        """Удаляет агента из реестра."""
        agent = self._agents.pop(name, None)
        if agent:
            logger.info(f"Агент удалён: {name}", extra={"event": "agent_unregistered"})
        return agent

    def get(self, name: str) -> Optional[BaseAgent]:
        """Возвращает агента по имени."""
        return self._agents.get(name)

    def find_by_capability(self, capability: str) -> list[BaseAgent]:
        """Находит агентов с указанной capability."""
        return [a for a in self._agents.values() if capability in a.capabilities]

    async def dispatch(self, task_type: str, **kwargs) -> Optional[TaskResult]:
        """Диспетчеризует задачу к подходящему агенту."""
        agents = self.find_by_capability(task_type)
        if not agents:
            logger.debug(
                f"Нет агента для capability: {task_type}",
                extra={"event": "dispatch_no_agent", "context": {"task_type": task_type}},
            )
            return None

        agent = agents[0]
        logger.info(
            f"Dispatch: {task_type} → {agent.name}",
            extra={"event": "dispatch", "context": {"task_type": task_type, "agent": agent.name}},
        )
        try:
            result = await agent.execute_task(task_type, **kwargs)
            agent._track_result(result)
            return result
        except Exception as e:
            logger.error(
                f"Ошибка dispatch {task_type} → {agent.name}: {e}",
                extra={"event": "dispatch_error"},
                exc_info=True,
            )
            return TaskResult(success=False, error=str(e))

    async def start_all(self) -> None:
        """Запускает все зарегистрированные агенты."""
        for agent in self._agents.values():
            try:
                await agent.start()
            except Exception as e:
                logger.error(f"Ошибка запуска {agent.name}: {e}", extra={"event": "agent_start_error"})

    async def stop_all(self) -> None:
        """Останавливает все агенты."""
        for agent in self._agents.values():
            try:
                await agent.stop()
            except Exception as e:
                logger.error(f"Ошибка остановки {agent.name}: {e}", extra={"event": "agent_stop_error"})

    def get_all_statuses(self) -> list[dict]:
        """Возвращает статусы всех агентов."""
        return [a.get_status() for a in self._agents.values()]

    @property
    def agents(self) -> dict[str, BaseAgent]:
        return dict(self._agents)
