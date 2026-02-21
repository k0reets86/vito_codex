"""SMMAgent — Agent 03: управление социальными сетями.

Dispatches to real platform objects (Twitter) when available.
Generates content via LLM, then posts to the actual platform.
"""

import time
from pathlib import Path
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("smm_agent", agent="smm_agent")
SUPPORTED_PLATFORMS = ["twitter", "instagram", "linkedin", "tiktok"]

SOCIAL_DIR = Path("/home/vito/vito-agent/output/social")
SOCIAL_DIR.mkdir(parents=True, exist_ok=True)


class SMMAgent(BaseAgent):
    def __init__(self, platforms: dict | None = None, **kwargs):
        super().__init__(name="smm_agent", description="Управление соцсетями: посты, хэштеги, планирование", **kwargs)
        self._scheduled_posts: list[dict] = []
        self._platforms = platforms or {}  # {"twitter": TwitterPlatform, ...}

    def set_platforms(self, platforms: dict) -> None:
        """Set platform objects for real posting."""
        self._platforms = platforms

    @property
    def capabilities(self) -> list[str]:
        return ["social_media", "scheduling"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("social_media", "create_post"):
                result = await self.create_post(kwargs.get("platform", "twitter"), kwargs.get("content", kwargs.get("step", "")))
            elif task_type == "scheduling":
                result = await self.schedule_post(kwargs.get("platform", "twitter"), kwargs.get("content", ""), kwargs.get("publish_at", ""))
            elif task_type == "suggest_hashtags":
                result = await self.suggest_hashtags(kwargs.get("content", ""), kwargs.get("platform", "twitter"))
            else:
                result = await self.create_post("twitter", kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_post(self, platform: str, content: str, style: str = None) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")

        style_note = f" Стиль: {style}." if style else ""
        char_limit = 280 if platform == "twitter" else 2200

        response = await self.llm_router.call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Создай пост для {platform} (макс {char_limit} символов).{style_note}\nТема: {content}",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")

        post_text = response.strip()

        # Save to file first
        ts = int(time.time())
        file_path = SOCIAL_DIR / f"{platform}_{ts}.txt"
        file_path.write_text(post_text, encoding="utf-8")

        # Try to post to real platform
        publish_result = None
        platform_obj = self._platforms.get(platform)

        if platform_obj:
            try:
                publish_result = await platform_obj.publish({"text": post_text})
                if publish_result.get("status") in ("published", "created"):
                    logger.info(
                        f"Posted to {platform}: {publish_result.get('url', publish_result.get('tweet_id', '?'))}",
                        extra={"event": "smm_post_published", "context": publish_result},
                    )
                    self._record_expense(0.005, f"SMM post: {platform}")
                    return TaskResult(
                        success=True,
                        output=publish_result,
                        cost_usd=0.005,
                        metadata={
                            "platform": platform,
                            "published": True,
                            "file_path": str(file_path),
                            **publish_result,
                        },
                    )
                else:
                    logger.warning(
                        f"Post to {platform} failed: {publish_result}",
                        extra={"event": "smm_post_fail"},
                    )
            except Exception as e:
                logger.error(f"Platform {platform} post error: {e}", exc_info=True)

        # No platform or posting failed — return generated content
        self._record_expense(0.005, f"SMM post: {platform}")
        return TaskResult(
            success=True,
            output=post_text,
            cost_usd=0.005,
            metadata={
                "platform": platform,
                "published": False,
                "file_path": str(file_path),
                "note": f"No {platform} platform configured" if not platform_obj else "Posting failed",
            },
        )

    async def schedule_post(self, platform: str, content: str, publish_at: str) -> TaskResult:
        post_result = await self.create_post(platform, content)
        if not post_result.success:
            return post_result
        entry = {"platform": platform, "content": post_result.output, "publish_at": publish_at, "status": "scheduled"}
        self._scheduled_posts.append(entry)
        return TaskResult(success=True, output={"scheduled": True, "platform": platform, "publish_at": publish_at, "post": post_result.output})

    async def suggest_hashtags(self, content: str, platform: str = "twitter") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=f"Подбери 15-20 хэштегов для {platform} по теме: {content[:500]}", estimated_tokens=500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.003)
