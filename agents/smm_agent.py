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
        return ["social_media", "scheduling", "campaign_plan"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("social_media", "create_post"):
                result = await self.create_post(kwargs.get("platform", "twitter"), kwargs.get("content", kwargs.get("step", "")))
            elif task_type == "scheduling":
                result = await self.schedule_post(kwargs.get("platform", "twitter"), kwargs.get("content", ""), kwargs.get("publish_at", ""))
            elif task_type == "campaign_plan":
                topic = kwargs.get("content", kwargs.get("step", "digital product launch"))
                tags = await self.suggest_hashtags(topic, kwargs.get("platform", "twitter"))
                post = await self.create_post(kwargs.get("platform", "twitter"), topic)
                result = TaskResult(
                    success=bool(tags.success and post.success),
                    output={
                        "platform": kwargs.get("platform", "twitter"),
                        "topic": topic,
                        "post": post.output,
                        "hashtags": tags.output,
                        "next_actions": [
                            "Опубликовать 1 основной пост",
                            "Сделать 1 follow-up через 6-12 часов",
                            "Собрать первые вопросы аудитории в комментариях",
                        ],
                    },
                )
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
        style_note = f" Стиль: {style}." if style else ""
        char_limit = 280 if platform == "twitter" else 2200

        post_text = ""
        if self.llm_router:
            response = await self._call_llm(
                task_type=TaskType.CONTENT,
                prompt=f"Создай пост для {platform} (макс {char_limit} символов).{style_note}\nТема: {content}",
                estimated_tokens=1000,
            )
            if response:
                post_text = response.strip()
        if not post_text:
            post_text = self._local_post(platform, content, style=style)

        # Save to file first
        ts = int(time.time())
        file_path = SOCIAL_DIR / f"{platform}_{ts}.txt"
        file_path.write_text(post_text, encoding="utf-8")

        # Try to post to real platform
        publish_result = None
        platform_obj = self._platforms.get(platform)

        if platform_obj:
            try:
                # Owner approval gate for any publication
                if self.comms:
                    import uuid
                    req_id = f"publish_{platform}_{uuid.uuid4().hex[:8]}"
                    approved = await self.comms.request_approval_with_files(
                        request_id=req_id,
                        message=(
                            f"[smm_agent] Запрос публикации в {platform}.\n"
                            f"Подтверди ✅ или отклони ❌.\n"
                            f"Текст:\n{post_text[:500]}"
                        ),
                        files=[str(file_path)],
                        timeout_seconds=3600,
                    )
                    if approved is not True:
                        return TaskResult(
                            success=False,
                            error="Owner approval rejected or timed out",
                            metadata={"platform": platform, "file_path": str(file_path)},
                        )
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
        response = None
        if self.llm_router:
            response = await self._call_llm(task_type=TaskType.CONTENT, prompt=f"Подбери 15-20 хэштегов для {platform} по теме: {content[:500]}", estimated_tokens=500)
        if not response:
            response = self._local_hashtags(content, platform)
            return TaskResult(success=True, output=response, metadata={"mode": "local_fallback"})
        return TaskResult(success=True, output=response, cost_usd=0.003)

    def _local_post(self, platform: str, content: str, style: str | None = None) -> str:
        topic = (content or "AI automation update").strip()
        tone = (style or "practical").strip().lower()
        core = f"{topic}: короткий разбор, что это дает на практике и как применить уже сегодня."
        cta = "Если нужно — дам готовый чеклист внедрения."
        text = f"{core} {cta}"
        if tone in {"bold", "aggressive"}:
            text = f"{topic}. Без воды: только шаги, которые дают результат. Писать \"план\" — пришлю сразу."
        if platform == "twitter":
            return text[:279]
        return text

    def _local_hashtags(self, content: str, platform: str) -> str:
        words = [w.lower() for w in str(content or "").replace(",", " ").split() if len(w) >= 4][:10]
        tags = ["#ai", "#automation", "#digitalproduct", "#growth", "#onlinebusiness"]
        for w in words:
            tag = "#" + "".join(ch for ch in w if ch.isalnum())
            if len(tag) > 2 and tag not in tags:
                tags.append(tag)
            if len(tags) >= 12:
                break
        if platform == "twitter":
            tags = tags[:8]
        return " ".join(tags)
