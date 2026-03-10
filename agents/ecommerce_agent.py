"""ECommerceAgent — Agent 05: управление листингами на платформах."""

import time
from typing import Any, Optional
from pathlib import Path

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings
from modules.platform_final_verifier import verify_platform_result
from modules.listing_optimizer import optimize_listing_payload
from modules.platform_artifact_pack import build_platform_bundle
from modules.platform_rules_sync import configured_services, sync_platform_rules
from modules.platform_knowledge import get_service_knowledge
from modules.platform_runbook_packs import build_service_runbook_pack
from modules.commerce_runtime import build_listing_runtime_profile
from modules.workflow_recipes import platform_recipe
from modules.workflow_recipe_executor import WorkflowRecipeExecutor

logger = get_logger("ecommerce_agent", agent="ecommerce_agent")


class ECommerceAgent(BaseAgent):
    NEEDS = {
        "listing_create": ["platform_runbook_pack", "platform_knowledge", "artifact_pack", "seo_pack"],
        "publish_package_build": ["content_creator", "seo_agent", "marketing_agent", "smm_agent"],
        "platform_rules_sync": ["platform_rules"],
        "*": ["platform_knowledge"],
    }

    def __init__(self, platforms: dict = None, registry=None, **kwargs):
        super().__init__(name="ecommerce_agent", description="Управление листингами (Gumroad, Etsy, Ko-fi)", **kwargs)
        self.platforms = platforms or {}
        self.registry = registry

    @property
    def capabilities(self) -> list[str]:
        return ["listing_create", "sales_check", "ecommerce", "publish_package_build", "platform_rules_sync"]

    def build_task_orchestration(self, task_type: str, **kwargs) -> dict:
        task = str(task_type or "").strip().lower()
        if task in {"listing_create", "ecommerce", "publish_package_build"}:
            return {
                "resources": ["platform_adapter", "content_creator", "seo_agent", "marketing_agent", "smm_agent"],
                "verify_with": "quality_review",
            }
        return {}

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("listing_create", "ecommerce"):
                result = await self.create_listing(kwargs.get("platform", "gumroad"), kwargs.get("data", kwargs))
            elif task_type == "publish_package_build":
                result = await self.build_publish_package(kwargs.get("platform", "gumroad"), kwargs.get("data", kwargs))
            elif task_type == "platform_rules_sync":
                result = await self.sync_platform_rules(kwargs.get("services"))
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

    async def _dispatch_registry(self, capability: str, **kwargs) -> Optional[TaskResult]:
        if not self.registry:
            return None
        try:
            return await self.registry.dispatch(capability, **kwargs)
        except Exception:
            return None

    async def build_publish_package(self, platform: str, data: dict) -> TaskResult:
        """Build full package via responsible collaborators (content+seo+marketing+smm)."""
        platform = str(platform or "gumroad").strip().lower()
        seed = build_platform_bundle(platform, data or {})
        package: dict[str, Any] = {
            "platform": platform,
            "payload": dict(seed),
            "contributors": [],
            "notes": [],
            "skill_pack": self.get_skill_pack(),
            "handled_by": "ecommerce_agent",
        }
        topic = str(seed.get("title") or seed.get("name") or "VITO Digital Product").strip()
        price = int(seed.get("price", 9) or 9)

        # 1) Content package (texts + files)
        turnkey = await self._dispatch_registry("product_turnkey", topic=topic, platform=platform, price=price)
        if turnkey and turnkey.success and isinstance(turnkey.output, dict):
            package["contributors"].append("content_creator")
            out = turnkey.output
            files = out.get("files") if isinstance(out.get("files"), dict) else {}
            listing = out.get("listing") if isinstance(out.get("listing"), dict) else {}
            payload = package["payload"]
            payload["title"] = str(listing.get("title") or payload.get("title") or topic)
            payload["name"] = payload["title"]
            payload["short_description"] = str(listing.get("short_description") or payload.get("short_description") or "")
            if files.get("pdf_path"):
                payload["pdf_path"] = str(files.get("pdf_path"))
            if files.get("cover_path"):
                payload["cover_path"] = str(files.get("cover_path"))
            if files.get("thumb_path"):
                payload["thumb_path"] = str(files.get("thumb_path"))
            if listing.get("tags"):
                payload["tags"] = list(listing.get("tags") or payload.get("tags") or [])
            if listing.get("category"):
                payload["category"] = str(listing.get("category"))
        else:
            package["notes"].append("content_creator_unavailable_or_failed")

        # 2) SEO pack (keywords/meta score)
        seo = await self._dispatch_registry(
            "listing_seo_pack",
            platform=platform,
            title=str(package["payload"].get("title") or topic),
            description=str(package["payload"].get("description") or ""),
            tags=package["payload"].get("tags") or [],
        )
        if seo and seo.success and isinstance(seo.output, dict):
            package["contributors"].append("seo_agent")
            so = seo.output
            payload = package["payload"]
            if so.get("tags"):
                payload["tags"] = list(so.get("tags"))
            if so.get("category"):
                payload["category"] = str(so.get("category"))
            payload["seo_title"] = str(so.get("seo_title") or payload.get("seo_title") or "")
            payload["seo_description"] = str(so.get("seo_description") or payload.get("seo_description") or "")
            payload["seo_score"] = int(so.get("seo_score") or payload.get("seo_score") or 0)
        else:
            package["notes"].append("seo_agent_unavailable_or_failed")

        # 3) Marketing + social launch notes
        mkt = await self._dispatch_registry(
            "marketing_strategy",
            product=topic,
            target_audience="US/EU digital buyers",
            budget_usd=100,
        )
        if mkt and mkt.success:
            package["contributors"].append("marketing_agent")
            package["marketing_strategy"] = mkt.output
        else:
            package["notes"].append("marketing_agent_unavailable_or_failed")

        smm = await self._dispatch_registry("campaign_plan", platform="twitter", content=topic)
        if smm and smm.success:
            package["contributors"].append("smm_agent")
            package["campaign_plan"] = smm.output
        else:
            package["notes"].append("smm_agent_unavailable_or_failed")

        package["payload"] = optimize_listing_payload(platform, package["payload"])
        package["payload"]["_package_ready"] = True
        return TaskResult(success=True, output=package)

    async def create_listing(self, platform: str, data: dict) -> TaskResult:
        platform = str(platform or "gumroad").strip().lower()
        knowledge = get_service_knowledge(platform)
        # Responsible agent behavior: always prepare full publish package first.
        if not bool((data or {}).get("_package_ready")):
            pkg = await self.build_publish_package(platform, data or {})
            if pkg and pkg.success and isinstance(pkg.output, dict):
                data = dict(pkg.output.get("payload") or {})
                data["_publish_contributors"] = list(pkg.output.get("contributors") or [])
            else:
                data = dict(data or {})
        data = optimize_listing_payload(platform, data or {})
        if knowledge:
            data["_platform_knowledge_context"] = {
                "recent_successes": list((knowledge.get("success_runbooks") or [])[-3:]),
                "recent_failures": list((knowledge.get("failure_runbooks") or [])[-3:]),
            }
            data["_platform_runbook_pack"] = build_service_runbook_pack(platform)
            data["_agent_skill_pack"] = self.get_skill_pack()
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
        if not preview_files and platform in {"gumroad", "etsy", "kofi"}:
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
            verification = verify_platform_result(
                platform,
                result or {},
                data or {},
                action="publish",
                require_evidence_for_success=True,
            )
            normalized = verification.normalized
            if isinstance(normalized, dict):
                normalized["verification"] = {
                    "ok": verification.ok,
                    "errors": list(verification.errors or []),
                }
            recipe = platform_recipe(platform)
            recipe_ok = True
            recipe_reason = ""
            if recipe:
                recipe_ok, recipe_reason = WorkflowRecipeExecutor._validate_acceptance(result or {}, recipe, data or {})
            accepted_statuses = {"ok", "success", "published", "created"}
            if bool(getattr(settings, "AUTONOMY_ACCEPT_INTERMEDIATE_PUBLISH_STATUSES", False)):
                accepted_statuses.update({"prepared", "created", "draft"})
            if status and status not in accepted_statuses:
                err = result.get("error") if isinstance(result, dict) else "unknown_error"
                logger.warning(
                    f"Листинг НЕ создан на {platform}: {status}",
                    extra={"event": "listing_failed", "context": {"platform": platform, "status": status}},
                )
                return TaskResult(success=False, error=err or f"publish_failed:{status}", output=result)
            if not verification.ok:
                err = ";".join(verification.errors)
                logger.warning(
                    f"Листинг НЕ принят по финальному verifier на {platform}",
                    extra={"event": "listing_contract_failed", "context": {"platform": platform, "errors": verification.errors, "status": status}},
                )
                return TaskResult(
                    success=False,
                    error=err,
                    output=normalized,
                    metadata={
                        "listing_runtime_profile": build_listing_runtime_profile(
                            platform=platform,
                            status=str(status or ""),
                            verification={"ok": False, "errors": verification.errors},
                            contributors=list(data.get("_publish_contributors") or []),
                        ),
                        **self.get_skill_pack(),
                    },
                )
            if recipe and not recipe_ok:
                logger.warning(
                    f"Листинг НЕ принят по recipe gate на {platform}",
                    extra={"event": "listing_recipe_failed", "context": {"platform": platform, "reason": recipe_reason, "status": status}},
                )
                return TaskResult(
                    success=False,
                    error=recipe_reason or "publish_recipe_gate_failed",
                    output=result,
                    metadata={
                        "listing_runtime_profile": build_listing_runtime_profile(
                            platform=platform,
                            status=str(status or ""),
                            verification={"ok": False, "errors": [recipe_reason or "publish_recipe_gate_failed"]},
                            contributors=list(data.get("_publish_contributors") or []),
                        ),
                        **self.get_skill_pack(),
                    },
                )
            logger.info(
                f"Листинг создан на {platform}",
                extra={"event": "listing_created", "context": {"platform": platform}},
            )
            if isinstance(result, dict) and data.get("_publish_contributors"):
                result["contributors"] = list(data.get("_publish_contributors") or [])
            if isinstance(result, dict) and knowledge:
                result["platform_knowledge_summary"] = {
                    "success_count": len(knowledge.get("success_runbooks") or []),
                    "failure_count": len(knowledge.get("failure_runbooks") or []),
                }
            if isinstance(result, dict):
                result["agent_skill_pack"] = self.get_skill_pack()
                result["handled_by"] = "ecommerce_agent"
            return TaskResult(
                success=True,
                output=result,
                metadata={
                    "listing_runtime_profile": build_listing_runtime_profile(
                        platform=platform,
                        status=str(status or ""),
                        verification={"ok": True, "errors": []},
                        contributors=list(data.get("_publish_contributors") or []),
                    ),
                    **self.get_skill_pack(),
                },
            )
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

    async def sync_platform_rules(self, services: list[str] | None = None) -> TaskResult:
        """Track official platform rule changes, update KB, notify owner in TG."""
        try:
            svc = services or configured_services() or ["gumroad", "etsy", "kofi", "printful", "reddit", "pinterest", "amazon_kdp", "twitter"]
            report = sync_platform_rules(services=list(svc))
            changed = int(report.get("changed_count", 0) or 0)
            if changed > 0 and self.comms:
                lines = ["Обнаружены изменения правил платформ:"]
                for ch in list(report.get("changes") or [])[:8]:
                    lines.append(f"- {ch.get('service')}: {ch.get('url')}")
                lines.append("Знания обновлены в platform_knowledge и platform_rules_updates.md")
                await self.comms.send_message("\n".join(lines), level="warning")
            return TaskResult(success=True, output=report)
        except Exception as e:
            return TaskResult(success=False, error=f"platform_rules_sync_failed: {e}")
