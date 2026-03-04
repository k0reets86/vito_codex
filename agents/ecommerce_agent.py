"""ECommerceAgent — Agent 05: управление листингами на платформах."""

import time
from typing import Any, Optional
from pathlib import Path

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings
from modules.listing_optimizer import optimize_listing_payload

logger = get_logger("ecommerce_agent", agent="ecommerce_agent")


class ECommerceAgent(BaseAgent):
    def __init__(self, platforms: dict = None, **kwargs):
        super().__init__(name="ecommerce_agent", description="Управление листингами (Gumroad, Etsy, Ko-fi)", **kwargs)
        self.platforms = platforms or {}

    @property
    def capabilities(self) -> list[str]:
        return ["listing_create", "sales_check", "ecommerce"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("listing_create", "ecommerce"):
                result = await self.create_listing(kwargs.get("platform", "gumroad"), kwargs.get("data", kwargs))
            elif task_type == "sales_check":
                result = await self.check_sales(kwargs.get("platform"))
            elif task_type == "update_listing":
                result = await self.update_listing(kwargs.get("platform", ""), kwargs.get("listing_id", ""), kwargs.get("data", {}))
            else:
                result = TaskResult(success=False, error=f"Неизвестный task_type: {task_type}")
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_listing(self, platform: str, data: dict) -> TaskResult:
        data = optimize_listing_payload(platform, data or {})
        if data.get("allow_existing_update"):
            target_id = str(data.get("target_product_id") or data.get("target_listing_id") or data.get("target_slug") or "").strip()
            if not target_id:
                return TaskResult(success=False, error="existing_update_requires_target_id")
        # Normalize minimal fields per platform
        if platform == "gumroad":
            if not data.get("category"):
                data["category"] = "Education"
            if not data.get("tags"):
                data["tags"] = ["ai", "automation", "productivity", "templates", "digital product"]
        # Owner approval gate for publication
        preview_files: list[str] = []
        for key in ("pdf_path", "cover_path", "thumb_path", "preview_path"):
            if data.get(key):
                preview_files.append(str(data.get(key)))
        if isinstance(data.get("preview_paths"), list):
            preview_files.extend([str(p) for p in data.get("preview_paths") if str(p).strip()])
        # Support image lists
        for key in ("images", "listing_images", "files"):
            if isinstance(data.get(key), list):
                preview_files.extend([str(p) for p in data.get(key)])
        # Keep only existing files
        preview_files = [p for p in preview_files if p and Path(p).exists()]
        if platform == "gumroad" and not data.get("pdf_path"):
            return TaskResult(success=False, error="Gumroad publish requires pdf_path")
        if not preview_files:
            return TaskResult(success=False, error="Preview files required before publication")
        if self.comms and bool(getattr(settings, "AUTONOMY_ECOMMERCE_APPROVAL_REQUIRED", False)):
            try:
                import uuid
                request_id = f"publish_{platform}_{uuid.uuid4().hex[:8]}"
                msg = (
                    f"[ecommerce_agent] Запрос публикации на {platform}.\n"
                    f"Подтверди ✅ или отклони ❌.\n"
                    f"Кратко: {str(data)[:300]}"
                )
                approved = await self.comms.request_approval_with_files(
                    request_id=request_id,
                    message=msg,
                    files=preview_files,
                    timeout_seconds=3600,
                )
                if approved is not True:
                    return TaskResult(success=False, error="Owner approval rejected or timed out")
            except Exception:
                return TaskResult(success=False, error="Owner approval failed")
        plat = self.platforms.get(platform)
        if not plat:
            return TaskResult(success=False, error=f"Платформа '{platform}' не зарегистрирована. Доступны: {list(self.platforms.keys())}")
        try:
            if hasattr(plat, "authenticate"):
                try:
                    authed = await plat.authenticate()
                    if not authed:
                        logger.warning(
                            f"Авторизация не подтверждена для {platform} перед publish",
                            extra={"event": "listing_auth_not_confirmed", "context": {"platform": platform}},
                        )
                except Exception:
                    logger.warning(
                        f"Ошибка auth precheck для {platform}",
                        extra={"event": "listing_auth_precheck_error", "context": {"platform": platform}},
                    )
            result = await plat.publish(data)
            status = result.get("status") if isinstance(result, dict) else None
            accepted_statuses = {"ok", "success", "published"}
            if bool(getattr(settings, "AUTONOMY_ACCEPT_INTERMEDIATE_PUBLISH_STATUSES", False)):
                accepted_statuses.update({"prepared", "created", "draft"})
            if status and status not in accepted_statuses:
                err = result.get("error") if isinstance(result, dict) else "unknown_error"
                logger.warning(
                    f"Листинг НЕ создан на {platform}: {status}",
                    extra={"event": "listing_failed", "context": {"platform": platform, "status": status}},
                )
                return TaskResult(success=False, error=err or f"publish_failed:{status}", output=result)
            logger.info(
                f"Листинг создан на {platform}",
                extra={"event": "listing_created", "context": {"platform": platform}},
            )
            return TaskResult(success=True, output=result)
        except Exception as e:
            return TaskResult(success=False, error=f"Ошибка создания листинга на {platform}: {e}")

    async def update_listing(self, platform: str, listing_id: str, data: dict) -> TaskResult:
        if not str(listing_id or "").strip():
            return TaskResult(success=False, error="update_requires_explicit_listing_id")
        plat = self.platforms.get(platform)
        if not plat:
            return TaskResult(success=False, error=f"Платформа '{platform}' не зарегистрирована")
        try:
            if hasattr(plat, "update"):
                result = await plat.update(listing_id, data)
                return TaskResult(success=True, output=result)
            return TaskResult(success=False, error=f"Платформа {platform} не поддерживает обновление")
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def check_sales(self, platform: str = None) -> TaskResult:
        results = {}
        platforms_to_check = [platform] if platform else list(self.platforms.keys())
        for p_name in platforms_to_check:
            plat = self.platforms.get(p_name)
            if plat:
                try:
                    analytics = await plat.get_analytics()
                    results[p_name] = analytics
                except Exception as e:
                    results[p_name] = {"error": str(e)}
        return TaskResult(success=True, output=results)
