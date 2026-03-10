from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from modules.autonomy_runtime import build_self_evolve_runtime_profile, score_improvement_proposal
from modules.owner_model import OwnerModel
from modules.reflector import VITOReflector
from modules.skill_library import VITOSkillLibrary


class SelfEvolver(BaseAgent):
    NEEDS = {
        "weekly_improve_cycle": ["technical_reflections", "skill_library", "devops_agent", "self_healer"],
        "propose_improvements": ["technical_reflections", "skill_library", "owner_model"],
        "*": ["technical_reflections"],
    }

    def __init__(self, **kwargs):
        super().__init__(name="self_evolver", description="Автономное улучшение VITO через безопасные предложения", **kwargs)
        self.reflector = VITOReflector()
        self.skill_lib = VITOSkillLibrary()
        self.owner_model = OwnerModel()

    @property
    def capabilities(self) -> list[str]:
        return ["weekly_improve_cycle", "propose_improvements"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        try:
            if task_type == "propose_improvements":
                output = await self.propose_improvements(kwargs.get("issues"))
            else:
                output = await self.weekly_improve_cycle()
            return TaskResult(success=True, output=output)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def weekly_improve_cycle(self) -> dict[str, Any]:
        issues = self.reflector.get_recent(n=15, category="technical")
        proposals = await self.propose_improvements(issues=issues)
        await self._notify_report(proposals)
        owner_profile = self.owner_model.get_preferences() if hasattr(self.owner_model, "get_preferences") else {}
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "issue_count": len(issues),
            "proposals": proposals,
            "runtime_profile": build_self_evolve_runtime_profile(
                proposal_count=len(proposals),
                issue_buckets=Counter(self._classify_issue(issue) for issue in issues),
                owner_alignment=bool(owner_profile),
            ),
        }

    async def propose_improvements(self, issues: list[str] | None = None) -> list[dict[str, Any]]:
        issues = issues or self.reflector.get_recent(n=15, category="technical")
        owner_profile = self.owner_model.get_preferences() if hasattr(self.owner_model, "get_preferences") else {}
        skills = self.skill_lib.list_all(limit=20)
        issue_types = Counter(self._classify_issue(issue) for issue in issues)
        top_skill_names = [str(item.get("name") or item.get("title") or "") for item in skills if item]

        proposals = [
            {
                "title": "Strengthen flaky browser and platform runbooks",
                "why": "Technical reflections still cluster around browser/platform instability.",
                "risk": "low",
                "type": "runtime_hardening",
                "evidence": {
                    "issue_count": len(issues),
                    "issue_buckets": issue_types,
                },
                "next_actions": [
                    "collect_failure_signatures",
                    "promote_verified_runbook_fix",
                    "tighten_final_verifier_contracts",
                ],
            },
            {
                "title": "Promote recurring successful patterns into default runtime skills",
                "why": f"Skill library now contains {len(skills)} tracked skills and should influence defaults more aggressively.",
                "risk": "low",
                "type": "skill_promotion",
                "evidence": {
                    "skill_count": len(skills),
                    "sample_skills": top_skill_names[:8],
                },
                "next_actions": [
                    "score_runtime_skills",
                    "promote_high_confidence_skills",
                    "attach_skills_to_agents",
                ],
            },
        ]

        if issues:
            proposals.append(
                {
                    "title": "Target the highest-frequency technical failure with a verified fix",
                    "why": issues[0][:300],
                    "risk": "medium",
                    "type": "verified_patch",
                    "evidence": {"top_failure": issues[0][:300], "issue_buckets": issue_types},
                    "next_actions": [
                        "cluster_failures",
                        "route_to_devops_agent",
                        "verify_fix_before_promotion",
                    ],
                }
            )

        if owner_profile:
            proposals.append(
                {
                    "title": "Align autonomy defaults to persistent owner preferences",
                    "why": "Owner model now stores long-lived preferences that should influence planning and product strategy.",
                    "risk": "low",
                    "type": "owner_alignment",
                    "evidence": {"owner_model_keys": sorted(list(owner_profile.keys()))[:12]},
                    "next_actions": [
                        "review_owner_preferences",
                        "update_default_runbooks",
                        "re_score_autonomy_goals",
                    ],
                }
            )
        ranked = []
        for item in proposals[:4]:
            enriched = dict(item)
            enriched.update(
                score_improvement_proposal(
                    issue_buckets=issue_types,
                    owner_alignment=bool(owner_profile),
                    skill_count=len(skills),
                    title=str(item.get("title") or ""),
                )
            )
            ranked.append(enriched)
        ranked.sort(key=lambda row: float(row.get("proposal_score", 0.0)), reverse=True)
        return ranked[:4]

    def _classify_issue(self, issue: str) -> str:
        low = str(issue or "").lower()
        if any(tok in low for tok in ["browser", "selector", "captcha", "page", "upload"]):
            return "browser"
        if any(tok in low for tok in ["memory", "retrieval", "skill"]):
            return "memory"
        if any(tok in low for tok in ["auth", "login", "token", "otp"]):
            return "auth"
        if any(tok in low for tok in ["platform", "etsy", "gumroad", "kdp", "printful"]):
            return "platform"
        return "general"

    async def _notify_report(self, proposals: list[dict[str, Any]]) -> None:
        if not self.comms:
            return
        lines = ["🔧 *VITO SelfEvolver — Еженедельный отчёт*", ""]
        for i, item in enumerate(proposals, start=1):
            lines.append(f"{i}. {item.get('title')}")
            lines.append(f"   why: {item.get('why')}")
        await self.comms.send_message("\n".join(lines))
