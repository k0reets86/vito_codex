"""AccountManager — Agent 20: управление аккаунтами на платформах."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings
from modules.account_auth_remediation import build_auth_remediation, build_platform_auth_pack

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
    NEEDS = {
        "account_management": ["credential_inventory", "profile_completion_runbooks"],
        "check_account": ["credential_inventory"],
        "email_code": ["inbox_access"],
        "*": ["account_state_memory"],
    }

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
            accounts.append({
                "platform": platform,
                "configured": configured,
                "env_var": env_var,
                "auth_pack": build_platform_auth_pack(platform),
                "next_actions": [] if configured else [f"set_env:{env_var}", f"profile_check:{platform}"],
            })
        return TaskResult(success=True, output={"account": "all", "auth_state": "inventory", "accounts": accounts, "skill_pack": self.get_skill_pack()})

    async def check_account(self, platform: str) -> TaskResult:
        env_var = PLATFORM_KEYS.get(platform)
        if not env_var:
            return TaskResult(success=True, output={"account": platform, "auth_state": "unknown_platform", "platform": platform, "status": "unknown_platform", "skill_pack": self.get_skill_pack()})
        configured = bool(getattr(settings, env_var, ""))
        remediation = build_auth_remediation(platform, configured=configured)
        return TaskResult(
            success=True,
            output={
                "account": platform,
                "auth_state": remediation["auth_state"],
                "platform": platform,
                "configured": configured,
                "env_var": env_var,
                "next_actions": remediation["next_actions"],
                "auth_pack": remediation["auth_pack"],
                "profile_completion_hint": f"browser_first_profile_check:{platform}",
                "skill_pack": self.get_skill_pack(),
            },
        )

    async def monitor_limits(self) -> TaskResult:
        limits = []
        for platform, env_var in PLATFORM_KEYS.items():
            configured = bool(getattr(settings, env_var, ""))
            limits.append({"platform": platform, "configured": configured, "api_limits": "unknown"})
        return TaskResult(success=True, output={"account": "all", "auth_state": "limits_snapshot", "limits": limits, "skill_pack": self.get_skill_pack()})

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
            remediation = build_auth_remediation("gmail", error="missing_credentials", configured=False)
            return TaskResult(success=True, output={"account": "gmail", **remediation, "skill_pack": self.get_skill_pack()})
        try:
            code, snippet = wait_for_code(
                address=address,
                password=password,
                from_filter=from_filter,
                subject_filter=subject_filter,
                prefer_link=prefer_link,
                timeout_sec=timeout_sec,
            )
        except Exception as e:
            remediation = build_auth_remediation("gmail", error=str(e), configured=True)
            return TaskResult(success=True, output={"account": "gmail", **remediation, "skill_pack": self.get_skill_pack()})
        if not code:
            remediation = build_auth_remediation("gmail", error="code_not_found", configured=True)
            return TaskResult(success=True, output={"account": "gmail", **remediation, "skill_pack": self.get_skill_pack()})
        return TaskResult(success=True, output={"account": "gmail", "auth_state": "code_fetched", "code": code, "snippet": snippet, "skill_pack": self.get_skill_pack()})
