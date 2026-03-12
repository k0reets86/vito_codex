"""QualityJudge — оценка качества контента перед публикацией.

Порог: score >= 7 — одобрено, < 7 — доработка.
"""

import json
import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings
from llm_router import TaskType
from modules.quality_runtime import build_quality_handoff_plan, build_quality_runtime_profile

logger = get_logger("quality_judge", agent="quality_judge")

APPROVAL_THRESHOLD = 7


class QualityJudge(BaseAgent):
    NEEDS = {
        "quality_review": ["content_pipeline", "publish_pipeline"],
        "content_check": ["content_pipeline"],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="quality_judge", description="Оценка качества контента (порог >= 7)", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["quality_review", "content_check"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        try:
            content = kwargs.get("content", kwargs.get("step", ""))
            content_type = kwargs.get("content_type", "article")
            result = await self.review(content, content_type)
            self._track_result(result)
            return result
        finally:
            self._status = AgentStatus.IDLE

    async def review(self, content: str, content_type: str = "article") -> TaskResult:
        start = time.monotonic()
        if not self.llm_router:
            local = self._local_review(content, content_type)
            duration_ms = int((time.monotonic() - start) * 1000)
            return TaskResult(success=True, output=local, duration_ms=duration_ms, metadata={"mode": "local_fallback"})
        prompt = (
            f"Оцени качество следующего контента (тип: {content_type}).\n\n"
            f"Контент:\n---\n{content[:5000]}\n---\n\n"
            f"Верни JSON: {{\"score\": 1-10, \"feedback\": \"описание\", \"issues\": [\"проблема1\"], "
            f"\"domain_scorecard\": {{\"completeness\": 1-10, \"evidence\": 1-10, \"compliance\": 1-10, \"readiness\": 1-10}}}}\n"
            f"Только JSON."
        )
        response = await self._call_llm(
            task_type=TaskType.CONTENT, prompt=prompt,
            system_prompt="Ты — строгий редактор. Оценивай объективно. JSON only.",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.005, f"Quality review: {content_type}")
        duration_ms = int((time.monotonic() - start) * 1000)
        # Parse
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
        except (json.JSONDecodeError, ValueError):
            data = {"score": 5, "feedback": response, "issues": []}
        score = data.get("score", 5)
        threshold = max(1, min(10, int(getattr(settings, "QUALITY_JUDGE_APPROVAL_THRESHOLD", APPROVAL_THRESHOLD) or APPROVAL_THRESHOLD)))
        result_output = {
            "score": score,
            "feedback": data.get("feedback", ""),
            "issues": data.get("issues", []),
        }
        raw_domain_scorecard = data.get("domain_scorecard")
        result_output["domain_scorecard"] = self._normalize_domain_scorecard(
            raw_domain_scorecard,
            content=str(content or ""),
            content_type=str(content_type or "article"),
        )
        domain_threshold = max(1, min(10, int(getattr(settings, "QUALITY_JUDGE_MIN_DOMAIN_THRESHOLD", threshold) or threshold)))
        blocked_dimensions = []
        if isinstance(raw_domain_scorecard, dict) and raw_domain_scorecard:
            blocked_dimensions = [
                key for key, value in dict(result_output["domain_scorecard"] or {}).items()
                if int(value or 0) < domain_threshold
            ]
        approved = bool(score >= threshold and not blocked_dimensions)
        result_output["threshold"] = threshold
        result_output["domain_threshold"] = domain_threshold
        result_output["blocked_dimensions"] = blocked_dimensions
        result_output["approved"] = approved
        result_output["recovery_plan"] = self._build_recovery_plan(
            issues=result_output["issues"],
            scorecard=result_output["domain_scorecard"],
            approved=approved,
        )
        result_output["handoff_plan"] = build_quality_handoff_plan(
            issues=result_output["issues"],
            scorecard=result_output["domain_scorecard"],
        )
        result_output["evidence"] = self._build_evidence(content=str(content or ""), content_type=str(content_type or "article"))
        logger.info(f"Quality review: score={score}, approved={approved}, threshold={threshold}", extra={"event": "quality_review", "context": result_output})
        return TaskResult(
            success=True,
            output=result_output,
            cost_usd=0.005,
            duration_ms=duration_ms,
            metadata={
                "quality_runtime_profile": build_quality_runtime_profile(
                    content_type=str(content_type or "article"),
                    score=score,
                    threshold=threshold,
                    approved=approved,
                    issues=result_output["issues"],
                    scorecard=result_output["domain_scorecard"],
                ),
                **self.get_skill_pack(),
            },
        )

    def _local_review(self, content: str, content_type: str) -> dict[str, Any]:
        text = (content or "").strip()
        issues = []
        score = 8
        if len(text) < 80:
            issues.append("content_too_short")
            score -= 3
        if "TODO" in text or "lorem ipsum" in text.lower():
            issues.append("placeholder_content")
            score -= 2
        if content_type in {"listing", "product"} and "http" not in text and len(text) < 180:
            issues.append("listing_lacks_depth")
            score -= 1
        threshold = max(1, min(10, int(getattr(settings, "QUALITY_JUDGE_APPROVAL_THRESHOLD", APPROVAL_THRESHOLD) or APPROVAL_THRESHOLD)))
        domain_scorecard = self._normalize_domain_scorecard(None, content=text, content_type=content_type)
        domain_threshold = max(1, min(10, int(getattr(settings, "QUALITY_JUDGE_MIN_DOMAIN_THRESHOLD", threshold) or threshold)))
        blocked_dimensions = [
            key for key, value in dict(domain_scorecard or {}).items()
            if int(value or 0) < domain_threshold
        ]
        approved = bool(score >= threshold and not blocked_dimensions)
        out = {
            "score": max(score, 1),
            "feedback": "Local heuristic review completed.",
            "approved": approved,
            "issues": issues,
            "domain_scorecard": domain_scorecard,
            "threshold": threshold,
            "domain_threshold": domain_threshold,
            "blocked_dimensions": blocked_dimensions,
            "recovery_plan": self._build_recovery_plan(issues=issues, scorecard=domain_scorecard, approved=approved),
            "evidence": self._build_evidence(content=text, content_type=content_type),
        }
        out["handoff_plan"] = build_quality_handoff_plan(
            issues=out["issues"],
            scorecard=out["domain_scorecard"],
        )
        return out

    def _normalize_domain_scorecard(self, raw: Any, *, content: str, content_type: str) -> dict[str, int]:
        scorecard = raw if isinstance(raw, dict) else {}
        text = str(content or "").strip()
        ctype = str(content_type or "").strip().lower()
        has_links = "http://" in text or "https://" in text
        has_depth = len(text) >= 180
        has_evidence_words = any(x in text.lower() for x in ("source", "evidence", "url", "report", "proof", "file", "tag"))
        compliance = 8
        readiness = 8
        if ctype in {"listing", "product", "product_pipeline_result", "publish", "listing_create"}:
            if not has_depth:
                readiness -= 2
            if not has_evidence_words:
                readiness -= 2
            if not has_links and ctype in {"publish", "product_pipeline_result"}:
                compliance -= 1
        defaults = {
            "completeness": 9 if has_depth else 6,
            "evidence": 8 if has_evidence_words else 5,
            "compliance": max(1, compliance),
            "readiness": max(1, readiness),
        }
        out: dict[str, int] = {}
        for key, fallback in defaults.items():
            try:
                value = int(scorecard.get(key, fallback))
            except Exception:
                value = int(fallback)
            out[key] = max(1, min(10, value))
        return out

    def _build_evidence(self, *, content: str, content_type: str) -> dict[str, Any]:
        text = str(content or "")
        return {
            "content_type": str(content_type or "article"),
            "content_length": len(text),
            "has_url": ("http://" in text or "https://" in text),
            "has_bullets": ("- " in text or "•" in text),
            "has_numbers": any(ch.isdigit() for ch in text),
        }

    def _build_recovery_plan(self, *, issues: list[Any], scorecard: dict[str, int], approved: bool) -> list[str]:
        if approved:
            return []
        steps: list[str] = []
        issue_set = {str(x or "").strip().lower() for x in issues}
        if "content_too_short" in issue_set or int(scorecard.get("completeness", 0)) < 7:
            steps.append("Expand the draft with concrete sections, examples, and completion of missing fields.")
        if "placeholder_content" in issue_set:
            steps.append("Replace placeholders with final copy and remove TODO/lorem ipsum fragments.")
        if int(scorecard.get("evidence", 0)) < 7:
            steps.append("Add evidence artifacts: links, file names, screenshots, or platform proof.")
        if int(scorecard.get("compliance", 0)) < 7:
            steps.append("Re-check platform policy, disclosure, and publishing constraints before release.")
        if int(scorecard.get("readiness", 0)) < 7:
            steps.append("Run one more editor reload verification before treating the object as done.")
        return steps or ["Revise the asset pack and rerun final verification."]
