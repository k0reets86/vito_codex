"""RiskAgent — Agent 12: оценка рисков, репутация, жалобы."""

import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("risk_agent", agent="risk_agent")


class RiskAgent(BaseAgent):
    NEEDS = {
        "risk_assessment": ["legal"],
        "reputation": ["analytics"],
        "complaint": ["legal"],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="risk_agent", description="Управление рисками: оценка, репутация, жалобы", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["risk_assessment", "reputation", "complaint"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "risk_assessment":
                result = await self.assess_risk(kwargs.get("action", kwargs.get("step", "")))
            elif task_type == "reputation":
                result = await self.monitor_reputation()
            elif task_type == "complaint":
                result = await self.handle_complaint(kwargs.get("complaint", {}))
            else:
                result = await self.assess_risk(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def assess_risk(self, action: str) -> TaskResult:
        local = self._local_risk_assessment(action)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Оцени риски действия: {action}\nОтветь в формате JSON:\n{{\"risk_level\": \"low/medium/high\", \"factors\": [...], \"recommendation\": \"...\"}}",
            estimated_tokens=1000,
        )
        if response:
            self._record_expense(0.01, f"Risk assessment: {action[:50]}")
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.01 if response else 0.0)

    async def monitor_reputation(self) -> TaskResult:
        local = self._local_reputation_monitor()
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.ROUTINE,
            prompt="Составь чеклист мониторинга репутации для AI-бизнеса:\n- Отзывы на платформах\n- Упоминания в соцсетях\n- Рейтинги\nДай текущий статус: positive/neutral/negative.",
            estimated_tokens=1000,
        )
        if response:
            local["llm_notes"] = response
        return TaskResult(success=True, output=local)

    async def handle_complaint(self, complaint: dict) -> TaskResult:
        local = self._local_complaint_response(complaint)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        complaint_text = "\n".join(f"{k}: {v}" for k, v in complaint.items())
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Составь ответ на жалобу клиента:\n{complaint_text}\nТон: вежливый, решение-ориентированный. Предложи компенсацию если уместно.",
            estimated_tokens=1000,
        )
        if response:
            local["llm_notes"] = response
        return TaskResult(success=True, output=local)

    def _local_risk_assessment(self, action: str) -> dict[str, Any]:
        text = (action or "").lower()
        factors = []
        score = 25
        if any(x in text for x in ("publish", "post", "listing", "upload")):
            factors.append("platform_policy_risk")
            score += 15
        if any(x in text for x in ("copyright", "meme", "brand", "trademark")):
            factors.append("ip_risk")
            score += 25
        if any(x in text for x in ("spam", "mass", "bulk", "automated")):
            factors.append("anti_abuse_risk")
            score += 25
        level = "low" if score < 35 else "medium" if score < 65 else "high"
        return {
            "action": action,
            "risk_level": level,
            "risk_score": score,
            "factors": factors or ["standard_execution_risk"],
            "recommendation": "Proceed with proof-of-work and platform-specific verification." if level != "high" else "Pause and request legal/policy review before proceeding.",
        }

    def _local_reputation_monitor(self) -> dict[str, Any]:
        return {
            "status": "neutral",
            "watchpoints": ["platform reviews", "social mentions", "chargebacks", "moderation events"],
            "escalate_if": ["negative review spike", "platform warnings", "ban signals"],
        }

    def _local_complaint_response(self, complaint: dict[str, Any]) -> dict[str, Any]:
        issue = str((complaint or {}).get("message") or "Customer issue").strip()
        kind = str((complaint or {}).get("type") or "general").strip()
        return {
            "complaint_type": kind,
            "response_template": (
                "Thanks for the feedback. We reviewed the issue and will resolve it quickly. "
                "Please reply with the order details so we can confirm the best next step."
            ),
            "recommended_resolution": "refund_or_fix_review" if kind in {"refund", "defect"} else "clarify_and_support",
            "issue_summary": issue,
        }
