"""SecurityAgent — Agent 13: аудит ключей, ротация, шифрование, сканирование."""

import os
import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("security_agent", agent="security_agent")

SENSITIVE_ENV_VARS = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY",
    "TELEGRAM_BOT_TOKEN", "GUMROAD_API_KEY", "ETSY_API_KEY",
    "MEDIUM_TOKEN", "WORDPRESS_APP_PASSWORD", "SENDGRID_API_KEY",
    "REDDIT_CLIENT_SECRET", "DATABASE_URL",
]


class SecurityAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="security_agent", description="Безопасность: аудит ключей, ротация, шифрование, уязвимости", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["security", "key_rotation"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("security", "audit"):
                result = await self.audit_keys()
            elif task_type == "key_rotation":
                result = await self.rotate_key(kwargs.get("service", ""))
            elif task_type == "scan":
                result = await self.scan_vulnerabilities()
            elif task_type == "encrypt":
                result = await self.encrypt_backup(kwargs.get("path", ""))
            else:
                result = await self.audit_keys()
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def audit_keys(self) -> TaskResult:
        report = {"configured": [], "missing": [], "weak": []}
        for var in SENSITIVE_ENV_VARS:
            value = os.environ.get(var, "")
            if value:
                report["configured"].append(var)
                if len(value) < 10:
                    report["weak"].append(var)
            else:
                report["missing"].append(var)
        report["total"] = len(SENSITIVE_ENV_VARS)
        report["configured_count"] = len(report["configured"])
        logger.info(f"Аудит ключей: {report['configured_count']}/{report['total']} настроено", extra={"event": "key_audit"})
        return TaskResult(success=True, output=report)

    async def rotate_key(self, service: str) -> TaskResult:
        logger.warning(f"Запрос ротации ключа: {service}", extra={"event": "key_rotation_request"})
        return TaskResult(success=True, output={"service": service, "status": "rotation_requested", "note": "Manual rotation required"})

    async def encrypt_backup(self, path: str) -> TaskResult:
        return TaskResult(success=True, output={"path": path, "status": "encryption_not_implemented"})

    async def scan_vulnerabilities(self) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        checks = []
        env_file = os.path.exists(".env")
        checks.append({"check": ".env file exists", "status": "found" if env_file else "not_found"})
        gitignore = os.path.exists(".gitignore")
        checks.append({"check": ".gitignore exists", "status": "ok" if gitignore else "warning"})
        response = await self._call_llm(
            task_type=TaskType.ROUTINE,
            prompt=f"Проанализируй результаты проверки безопасности и дай рекомендации:\n{checks}",
            estimated_tokens=500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output={"checks": checks, "analysis": response})
