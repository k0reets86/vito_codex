"""SecurityAgent — Agent 13: аудит ключей, ротация, шифрование, сканирование."""

import os
import time
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.ops_runtime import build_security_runtime_profile

logger = get_logger("security_agent", agent="security_agent")

SENSITIVE_ENV_VARS = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY",
    "TELEGRAM_BOT_TOKEN", "GUMROAD_API_KEY", "ETSY_API_KEY",
    "MEDIUM_TOKEN", "WORDPRESS_APP_PASSWORD", "SENDGRID_API_KEY",
    "REDDIT_CLIENT_SECRET", "DATABASE_URL",
]


class SecurityAgent(BaseAgent):
    NEEDS = {
        "security": ["runtime_maintenance_pipeline"],
        "scan": ["security"],
        "key_rotation": [],
        "default": [],
    }

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
        report["risk_score"] = max(0, min(10, 10 - len(report["missing"]) - len(report["weak"])))
        report["recovery_hints"] = [
            "Fill missing critical secrets before enabling live automation on affected platforms.",
            "Rotate weak or short credentials and re-check runtime secret health.",
        ]
        logger.info(f"Аудит ключей: {report['configured_count']}/{report['total']} настроено", extra={"event": "key_audit"})
        return TaskResult(success=True, output=report, metadata={
            "security_runtime_profile": build_security_runtime_profile(
                operation="audit_keys",
                risk_score=report["risk_score"],
                missing_count=len(report["missing"]),
                weak_count=len(report["weak"]),
                block_recommended=bool(report["missing"] or report["weak"]),
            ),
        })

    async def rotate_key(self, service: str) -> TaskResult:
        logger.warning(f"Запрос ротации ключа: {service}", extra={"event": "key_rotation_request"})
        return TaskResult(success=True, output={
            "service": service,
            "status": "rotation_requested",
            "note": "Manual rotation required",
            "recovery_hints": [
                "Create new secret, update runtime env, then revoke the old credential.",
                "Verify dependent platform logins after rotation completes.",
            ],
        }, metadata={
            "security_runtime_profile": build_security_runtime_profile(
                operation="rotate_key",
                risk_score=5,
                missing_count=0,
                weak_count=0,
                block_recommended=False,
            ),
        })

    async def encrypt_backup(self, path: str) -> TaskResult:
        return TaskResult(success=True, output={"path": path, "status": "encryption_not_implemented"})

    async def scan_vulnerabilities(self) -> TaskResult:
        checks = []
        env_file = os.path.exists(".env")
        checks.append({"check": ".env file exists", "status": "found" if env_file else "not_found"})
        gitignore = os.path.exists(".gitignore")
        checks.append({"check": ".gitignore exists", "status": "ok" if gitignore else "warning"})
        local = {
            "checks": checks,
            "analysis": {
                "status": "review_required" if any(c["status"] != "ok" for c in checks) else "ok",
                "recommendations": [
                    "Ensure secrets are not stored in git",
                    "Review missing environment variables",
                    "Keep runtime key rotation policy current",
                ],
            },
        }
        if not self.llm_router:
            local["analysis"]["recovery_hints"] = [
                "Confirm secrets are not tracked in git history.",
                "Close missing env gaps before re-running live integrations.",
            ]
            return TaskResult(success=True, output=local, metadata={
                "mode": "local_fallback",
                "security_runtime_profile": build_security_runtime_profile(
                    operation="scan_vulnerabilities",
                    risk_score=4 if any(c["status"] != "ok" for c in checks) else 8,
                    weak_count=sum(1 for c in checks if c["status"] != "ok"),
                    block_recommended=any(c["status"] != "ok" for c in checks),
                ),
            })
        response = await self._call_llm(
            task_type=TaskType.ROUTINE,
            prompt=f"Проанализируй результаты проверки безопасности и дай рекомендации:\n{checks}",
            estimated_tokens=500,
        )
        if response:
            local["analysis"]["llm_notes"] = response
        local["analysis"]["recovery_hints"] = [
            "Fix warnings in priority order: secrets exposure, missing envs, then policy drift.",
            "Re-run security scan after each remediation batch.",
        ]
        return TaskResult(success=True, output=local, metadata={
            "security_runtime_profile": build_security_runtime_profile(
                operation="scan_vulnerabilities",
                risk_score=4 if any(c["status"] != "ok" for c in checks) else 8,
                weak_count=sum(1 for c in checks if c["status"] != "ok"),
                block_recommended=any(c["status"] != "ok" for c in checks),
            ),
        })
