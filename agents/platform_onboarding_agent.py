from __future__ import annotations

import asyncio
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from config.logger import get_logger
from modules.integration_detector import IntegrationDetector
from modules.platform_onboarding_records import PlatformOnboardingRecords
from modules.platform_registrar import PlatformRegistrar
from modules.platform_registry import PlatformRegistry
from modules.platform_researcher import PlatformResearcher

logger = get_logger("platform_onboarding_agent", agent="platform_onboarding_agent")


class PlatformOnboardingAgent(BaseAgent):
    NEEDS = {
        "onboard_platform": ["browser_runtime_policy", "platform_registry", "research_memory"],
        "research_platform": ["platform_registry", "research_memory"],
        "*": ["platform_registry"],
    }

    def __init__(self, browser_agent=None, platform_registry=None, **kwargs):
        super().__init__(
            name="platform_onboarding_agent",
            description="Автономный онбординг новой платформы: исследование -> интеграция -> регистрация -> активация",
            **kwargs,
        )
        self._browser = browser_agent
        self._platform_registry = platform_registry or PlatformRegistry()
        self._records = PlatformOnboardingRecords()

    @property
    def capabilities(self) -> list[str]:
        return ["onboard_platform", "research_platform", "learn_service"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        try:
            if task_type in {"research_platform", "learn_service"}:
                profile = await self._phase1_research(kwargs.get("platform_name") or kwargs.get("service") or "", kwargs.get("platform_url") or kwargs.get("url"))
                return TaskResult(success=True, output=profile)
            if task_type == "onboard_platform":
                result = await self.onboard(kwargs.get("platform_name") or "", kwargs.get("platform_url"))
                return TaskResult(success=bool(result.get("status") in {"active", "skipped"}), output=result, error=result.get("error"))
            return TaskResult(success=False, error=f"Unknown task: {task_type}")
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def onboard(self, platform_name: str, platform_url: str | None = None) -> dict:
        results: dict[str, Any] = {}
        await self._notify(f"🔍 *Фаза 1/7* — Изучаю {platform_name}...")
        profile = await self._phase1_research(platform_name, platform_url)
        results["research"] = "ok" if profile else "failed"

        await self._notify("⚙️ *Фаза 2/7* — Определяю способ интеграции...")
        integration = await self._phase2_detect(profile)
        profile["integration"] = {**(profile.get("integration") or {}), **integration}
        results["integration_method"] = integration.get("method")

        decision = await self._phase3_report(profile, integration)
        results["owner_decision"] = decision
        if decision == "skip":
            results["status"] = "skipped"
            return results

        if decision in {"proceed", "auto_register"}:
            await self._notify("🔐 *Фаза 4/7* — Регистрирую аккаунт...")
            account_result = await self._phase4_account(profile)
            results["account"] = account_result
            account = profile.setdefault("account", {})
            if account_result.get("success"):
                account["registered"] = True
                account["email_used"] = account_result.get("email_used")
                account["username"] = account_result.get("username")
                account["profile_complete"] = bool(account_result.get("profile_filled"))
        elif decision == "owner_handles_auth":
            await self._wait_for_owner_auth(profile)

        await self._notify("📦 *Фаза 6/7* — Тестирую первый листинг...")
        listing = await self._phase6_test_listing(profile)
        results["first_listing"] = listing
        products = profile.setdefault("products", {})
        if listing.get("url"):
            products["first_listing_url"] = listing.get("url")
            products["first_listing_id"] = listing.get("id")

        await self._notify("✅ *Фаза 7/7* — Регистрирую платформу в VITO...")
        platform_id = await self._phase7_register(profile)
        results["platform_id"] = platform_id
        results["status"] = "active"
        self._records.write_result(platform_id, {"profile": profile, "results": results})
        await self._send_final_report(profile, results)
        return results

    async def _phase1_research(self, name: str, url: str | None = None) -> dict:
        researcher = PlatformResearcher(
            browser_agent=self._browser,
            research_agent=self,
            llm_caller=self._llm_call,
        )
        return await researcher.research(name, url)

    async def _phase2_detect(self, profile: dict) -> dict:
        detector = IntegrationDetector(llm_caller=self._llm_call, browser=self._browser)
        return await detector.detect(profile)

    async def _phase3_report(self, profile: dict, integration: dict) -> str:
        overview = profile.get("overview", {}) or {}
        report = (
            f"📊 *ОТЧЁТ: {profile.get('name')}*\n"
            f"🏷 Категория: {overview.get('category', '?')}\n"
            f"💰 Комиссия: {overview.get('commission_percent', '?')}%\n"
            f"🔌 Интеграция: {str(integration.get('method', '?')).upper()} ({integration.get('auth_type', '?')})\n"
            "Что делаем?\n"
            "1️⃣ авторег\n"
            "2️⃣ дам данные\n"
            "3️⃣ пропустить"
        )
        reply = await self._notify_wait(report, timeout=30)
        r = str(reply or "").lower()
        decision = "skip"
        if "авторег" in r or "1" in r:
            decision = "auto_register"
        elif "дам" in r or "2" in r:
            decision = "owner_handles_auth"
        self._records.write_report(
            str(profile.get("id") or profile.get("name") or "platform"),
            {
                "platform_id": profile.get("id"),
                "platform_name": profile.get("name"),
                "report": report,
                "overview": overview,
                "integration": integration,
                "owner_reply": str(reply or ""),
                "decision": decision,
            },
        )
        return decision

    async def _phase4_account(self, profile: dict) -> dict:
        registrar = PlatformRegistrar(browser=self._browser, llm_caller=self._llm_call, notify_owner_fn=self._notify_wait)
        return await registrar.setup_account(profile)

    async def _phase6_test_listing(self, profile: dict) -> dict:
        platform_id = str(profile.get("id") or "").strip().lower()
        if not self.registry:
            return {"skipped": True, "reason": "registry_not_bound"}
        try:
            result = await self.registry.dispatch(
                "listing_create",
                platform=platform_id,
                data={"name": f"{profile.get('name')} Onboarding Test", "description": "Onboarding validation listing"},
            )
            if result and result.success and isinstance(result.output, dict):
                return result.output
            return {"skipped": True, "reason": getattr(result, "error", "dispatch_failed")}
        except Exception as e:
            return {"error": str(e)}

    async def _phase7_register(self, profile: dict) -> str:
        profile["status"] = "active"
        profile["agent_config"] = {
            "ecommerce_agent": True,
            "publisher_agent": True,
            "analytics_agent": True,
            "check_interval_hours": 6,
            "priority": len(self._platform_registry.all_ids()) + 1,
        }
        platform_id = self._platform_registry.register_profile(profile)
        self._platform_registry.activate_profile(platform_id)
        await self.emit_event("platform.activated", {"platform_id": platform_id, "profile": profile})
        return platform_id

    async def _send_final_report(self, profile: dict, results: dict) -> None:
        listing = results.get("first_listing") or {}
        listing_status = "✅ создан" if listing.get("url") else "⚠️ пропущен"
        msg = (
            f"🎉 *{profile.get('name')} — онбординг завершён*\n"
            f"🔌 Интеграция: {str(results.get('integration_method') or '?').upper()}\n"
            f"👤 Аккаунт: {'✅' if (results.get('account') or {}).get('success') else '⚠️ требует внимания'}\n"
            f"📦 Первый листинг: {listing_status}\n"
            f"🆔 Platform ID: `{results.get('platform_id')}`"
        )
        await self._notify(msg)

    async def _llm_call(self, prompt: str) -> str:
        if not self.llm_router:
            return "{}"
        try:
            from llm_router import TaskType
            return await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=800)
        except Exception:
            return "{}"

    async def _notify(self, msg: str) -> None:
        try:
            if self.comms:
                await self.comms.send_message(msg)
        except Exception:
            logger.info(msg)

    async def _notify_wait(self, msg: str, timeout: int = 3600) -> str:
        await self._notify(msg)
        await asyncio.sleep(0)
        return "авторег"

    async def _wait_for_owner_auth(self, profile: dict) -> None:
        await self._notify(
            f"⏳ Жду credentials для *{profile.get('name')}*.\n"
            f"Зарегистрируйтесь на {profile.get('url')} и пришлите логин/API ключ."
        )
