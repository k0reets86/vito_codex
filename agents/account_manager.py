"""AccountManager — Agent 20: управление аккаунтами на платформах."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings

logger = get_logger("account_manager", agent="account_manager")

PLATFORM_KEYS = {
    "gumroad": "GUMROAD_API_KEY",
    "etsy": "ETSY_API_KEY",
    "kofi": "KOFI_API_KEY",
    "wordpress": "WORDPRESS_APP_PASSWORD",
    "medium": "MEDIUM_TOKEN",
    "telegram": "TELEGRAM_BOT_TOKEN",
}


class AccountManager(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="account_manager", description="Управление аккаунтами: статус, лимиты, мониторинг", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["account_management", "email_code"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("account_management", "list_accounts"):
                result = await self.list_accounts()
            elif task_type == "check_account":
                result = await self.check_account(kwargs.get("platform", ""))
            elif task_type == "monitor_limits":
                result = await self.monitor_limits()
            elif task_type == "email_code":
                result = await self.fetch_email_code(
                    from_filter=kwargs.get("from_filter", ""),
                    subject_filter=kwargs.get("subject_filter", ""),
                    prefer_link=bool(kwargs.get("prefer_link", False)),
                    timeout_sec=int(kwargs.get("timeout_sec", 120)),
                )
            else:
                result = await self.list_accounts()
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def list_accounts(self) -> TaskResult:
        accounts = []
        for platform, env_var in PLATFORM_KEYS.items():
            configured = bool(getattr(settings, env_var, ""))
            accounts.append({"platform": platform, "configured": configured, "env_var": env_var})
        return TaskResult(success=True, output=accounts)

    async def check_account(self, platform: str) -> TaskResult:
        env_var = PLATFORM_KEYS.get(platform)
        if not env_var:
            return TaskResult(success=True, output={"platform": platform, "status": "unknown_platform"})
        configured = bool(getattr(settings, env_var, ""))
        return TaskResult(success=True, output={"platform": platform, "configured": configured, "env_var": env_var})

    async def monitor_limits(self) -> TaskResult:
        limits = []
        for platform, env_var in PLATFORM_KEYS.items():
            configured = bool(getattr(settings, env_var, ""))
            limits.append({"platform": platform, "configured": configured, "api_limits": "unknown"})
        return TaskResult(success=True, output=limits)

    async def fetch_email_code(
        self,
        from_filter: str = "",
        subject_filter: str = "",
        prefer_link: bool = False,
        timeout_sec: int = 120,
    ) -> TaskResult:
        """Fetch verification code or link from email inbox."""
        from modules.email_inbox import wait_for_code
        address = settings.GMAIL_ADDRESS
        password = settings.GMAIL_PASSWORD
        if not address or not password:
            return TaskResult(success=False, error="GMAIL_ADDRESS/GMAIL_PASSWORD not set")
        code, snippet = wait_for_code(
            address=address,
            password=password,
            from_filter=from_filter,
            subject_filter=subject_filter,
            prefer_link=prefer_link,
            timeout_sec=timeout_sec,
        )
        if not code:
            return TaskResult(success=False, error="code_not_found")
        return TaskResult(success=True, output={"code": code, "snippet": snippet})
