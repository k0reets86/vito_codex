"""PublisherAgent — Agent 22: публикация на WordPress/Medium с QualityJudge."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger

logger = get_logger("publisher_agent", agent="publisher_agent")


class PublisherAgent(BaseAgent):
    def __init__(self, quality_judge=None, platforms: dict = None, **kwargs):
        super().__init__(name="publisher_agent", description="Публикация контента: WordPress, Medium", **kwargs)
        self.quality_judge = quality_judge
        self.platforms = platforms or {}

    @property
    def capabilities(self) -> list[str]:
        return ["publish", "wordpress"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            platform = kwargs.get("platform", "wordpress")
            if platform == "wordpress":
                result = await self.publish_wordpress(kwargs.get("title", ""), kwargs.get("content", ""), kwargs.get("tags"))
            elif platform == "medium":
                result = await self.publish_medium(kwargs.get("title", ""), kwargs.get("content", ""), kwargs.get("tags"))
            else:
                result = TaskResult(success=False, error=f"Неизвестная платформа: {platform}")
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def _check_quality(self, content: str, content_type: str = "article") -> TaskResult:
        if not self.quality_judge:
            return TaskResult(success=True, output={"score": 10, "approved": True, "feedback": "No judge"})
        return await self.quality_judge.review(content, content_type)

    async def publish_wordpress(self, title: str, content: str, tags: list[str] = None) -> TaskResult:
        quality = await self._check_quality(content)
        if quality.success and not quality.output.get("approved", True):
            logger.warning(f"Качество не прошло: score={quality.output.get('score')}", extra={"event": "quality_rejected"})
            return TaskResult(success=False, error=f"Качество контента ниже порога: {quality.output.get('score')}/10. {quality.output.get('feedback', '')}")
        wp = self.platforms.get("wordpress")
        if not wp:
            return TaskResult(success=False, error="WordPress платформа не подключена")
        try:
            result = await wp.publish({"title": title, "content": content, "tags": tags or []})
            logger.info(f"Опубликовано на WordPress: {title}", extra={"event": "wp_published"})
            return TaskResult(success=True, output=result)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def publish_medium(self, title: str, content: str, tags: list[str] = None) -> TaskResult:
        quality = await self._check_quality(content)
        if quality.success and not quality.output.get("approved", True):
            return TaskResult(success=False, error=f"Качество ниже порога: {quality.output.get('score')}/10")
        medium = self.platforms.get("medium")
        if not medium:
            return TaskResult(success=False, error="Medium платформа не подключена")
        try:
            result = await medium.publish({"title": title, "content": content, "tags": tags or []})
            return TaskResult(success=True, output=result)
        except Exception as e:
            return TaskResult(success=False, error=str(e))
