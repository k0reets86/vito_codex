"""PublisherAgent — Agent 22: публикация на WordPress/Medium с QualityJudge."""

import time
from typing import Any, Optional
from pathlib import Path
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from modules.commerce_runtime import build_publisher_runtime_profile

logger = get_logger("publisher_agent", agent="publisher_agent")


def _publisher_failure_profile(platform: str, reason: str, *, retryable: bool, stage: str) -> dict[str, Any]:
    return {
        "platform": str(platform or "").strip(),
        "approved": False,
        "quality_score": None,
        "retryable": bool(retryable),
        "stage": str(stage or "publish"),
        "reason": str(reason or "").strip() or "unknown_failure",
    }


class PublisherAgent(BaseAgent):
    NEEDS = {
        "publish": ["quality_judge", "publisher_platform", "approval_preview"],
        "*": ["publisher_runbooks"],
    }

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
        if self.comms:
            try:
                import uuid
                # Create preview file for full approval
                preview_dir = Path("/home/vito/vito-agent/output/previews")
                preview_dir.mkdir(parents=True, exist_ok=True)
                preview_path = preview_dir / f"wordpress_preview_{uuid.uuid4().hex[:8]}.md"
                preview_path.write_text(
                    f"# {title}\n\n{content}\n\nTags: {', '.join(tags or [])}\n",
                    encoding="utf-8",
                )
                request_id = f"publish_wordpress_{uuid.uuid4().hex[:8]}"
                msg = (
                    f"[publisher_agent] Запрос публикации WordPress.\n"
                    f"Подтверди ✅ или отклони ❌.\n"
                    f"Title: {title[:120]}"
                )
                approved = await self.comms.request_approval_with_files(
                    request_id=request_id,
                    message=msg,
                    files=[str(preview_path)],
                    timeout_seconds=3600,
                )
                if approved is not True:
                    return TaskResult(
                        success=False,
                        error="Owner approval rejected or timed out",
                        metadata={"publisher_runtime_profile": _publisher_failure_profile("wordpress", "owner_approval_rejected", retryable=True, stage="approval")},
                    )
            except Exception:
                return TaskResult(
                    success=False,
                    error="Owner approval failed",
                    metadata={"publisher_runtime_profile": _publisher_failure_profile("wordpress", "owner_approval_failed", retryable=True, stage="approval")},
                )
        quality = await self._check_quality(content)
        if quality.success and not quality.output.get("approved", True):
            logger.warning(f"Качество не прошло: score={quality.output.get('score')}", extra={"event": "quality_rejected"})
            return TaskResult(
                success=False,
                error=f"Качество контента ниже порога: {quality.output.get('score')}/10. {quality.output.get('feedback', '')}",
                metadata={"publisher_runtime_profile": _publisher_failure_profile("wordpress", "quality_rejected", retryable=True, stage="quality_gate")},
            )
        wp = self.platforms.get("wordpress")
        if not wp:
            return TaskResult(
                success=False,
                error="WordPress платформа не подключена",
                metadata={"publisher_runtime_profile": _publisher_failure_profile("wordpress", "platform_missing", retryable=False, stage="platform_lookup")},
            )
        try:
            result = await wp.publish({"title": title, "content": content, "tags": tags or []})
            logger.info(f"Опубликовано на WordPress: {title}", extra={"event": "wp_published"})
            return TaskResult(
                success=True,
                output={
                    "handled_by": "publisher_agent",
                    "platform": "wordpress",
                    "publish_result": result,
                    "quality_score": (quality.output or {}).get("score") if quality.success else None,
                    "skill_pack": self.get_skill_pack(),
                },
                metadata={
                    "publisher_runtime_profile": build_publisher_runtime_profile(
                        platform="wordpress",
                        quality_score=(quality.output or {}).get("score") if quality.success else None,
                        approved=bool((quality.output or {}).get("approved", True)) if quality.success else True,
                    ),
                    **self.get_skill_pack(),
                },
            )
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                metadata={"publisher_runtime_profile": _publisher_failure_profile("wordpress", str(e), retryable=True, stage="publish")},
            )

    async def publish_medium(self, title: str, content: str, tags: list[str] = None) -> TaskResult:
        if self.comms:
            try:
                import uuid
                preview_dir = Path("/home/vito/vito-agent/output/previews")
                preview_dir.mkdir(parents=True, exist_ok=True)
                preview_path = preview_dir / f"medium_preview_{uuid.uuid4().hex[:8]}.md"
                preview_path.write_text(
                    f"# {title}\n\n{content}\n\nTags: {', '.join(tags or [])}\n",
                    encoding="utf-8",
                )
                request_id = f"publish_medium_{uuid.uuid4().hex[:8]}"
                msg = (
                    f"[publisher_agent] Запрос публикации Medium.\n"
                    f"Подтверди ✅ или отклони ❌.\n"
                    f"Title: {title[:120]}"
                )
                approved = await self.comms.request_approval_with_files(
                    request_id=request_id,
                    message=msg,
                    files=[str(preview_path)],
                    timeout_seconds=3600,
                )
                if approved is not True:
                    return TaskResult(
                        success=False,
                        error="Owner approval rejected or timed out",
                        metadata={"publisher_runtime_profile": _publisher_failure_profile("medium", "owner_approval_rejected", retryable=True, stage="approval")},
                    )
            except Exception:
                return TaskResult(
                    success=False,
                    error="Owner approval failed",
                    metadata={"publisher_runtime_profile": _publisher_failure_profile("medium", "owner_approval_failed", retryable=True, stage="approval")},
                )
        quality = await self._check_quality(content)
        if quality.success and not quality.output.get("approved", True):
            return TaskResult(
                success=False,
                error=f"Качество ниже порога: {quality.output.get('score')}/10",
                metadata={"publisher_runtime_profile": _publisher_failure_profile("medium", "quality_rejected", retryable=True, stage="quality_gate")},
            )
        medium = self.platforms.get("medium")
        if not medium:
            return TaskResult(
                success=False,
                error="Medium платформа не подключена",
                metadata={"publisher_runtime_profile": _publisher_failure_profile("medium", "platform_missing", retryable=False, stage="platform_lookup")},
            )
        try:
            result = await medium.publish({"title": title, "content": content, "tags": tags or []})
            return TaskResult(
                success=True,
                output={
                    "handled_by": "publisher_agent",
                    "platform": "medium",
                    "publish_result": result,
                    "quality_score": (quality.output or {}).get("score") if quality.success else None,
                    "skill_pack": self.get_skill_pack(),
                },
                metadata={
                    "publisher_runtime_profile": build_publisher_runtime_profile(
                        platform="medium",
                        quality_score=(quality.output or {}).get("score") if quality.success else None,
                        approved=bool((quality.output or {}).get("approved", True)) if quality.success else True,
                    ),
                    **self.get_skill_pack(),
                },
            )
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                metadata={"publisher_runtime_profile": _publisher_failure_profile("medium", str(e), retryable=True, stage="publish")},
            )
