"""Runtime helpers for quality adjudication and escalation."""

from __future__ import annotations

from typing import Any


def build_quality_runtime_profile(
    *,
    content_type: str,
    score: int,
    threshold: int,
    approved: bool,
    issues: list[str] | None,
    scorecard: dict[str, int] | None,
) -> dict[str, Any]:
    issue_list = [str(x).strip() for x in (issues or []) if str(x).strip()]
    card = dict(scorecard or {})
    weak_domains = [k for k, v in card.items() if int(v or 0) < 7]
    escalation_targets = []
    if "compliance" in weak_domains:
        escalation_targets.extend(["legal_agent", "risk_agent"])
    if "evidence" in weak_domains:
        escalation_targets.append("analytics_agent")
    if "readiness" in weak_domains:
        escalation_targets.extend(["quality_judge", "publisher_agent"])
    if "completeness" in weak_domains:
        escalation_targets.extend(["content_creator", "seo_agent"])
    return {
        "content_type": str(content_type or "").strip() or "unknown",
        "score": int(score or 0),
        "threshold": int(threshold or 0),
        "approved": bool(approved),
        "issue_count": len(issue_list),
        "issues": issue_list,
        "weak_domains": weak_domains,
        "escalation_targets": list(dict.fromkeys(escalation_targets)),
        "next_actions": (
            ["approve_for_next_stage", "log_quality_decision", "attach_evidence_to_workflow"]
            if approved
            else ["open_rework_lane", "route_to_domain_agents", "rerun_final_verifier"]
        ),
    }


def build_quality_handoff_plan(
    *,
    issues: list[str] | None,
    scorecard: dict[str, int] | None,
) -> list[dict[str, str]]:
    issue_list = {str(x).strip().lower() for x in (issues or []) if str(x).strip()}
    card = dict(scorecard or {})
    plan: list[dict[str, str]] = []
    if int(card.get("completeness", 0)) < 7 or "content_too_short" in issue_list:
        plan.append({"agent": "content_creator", "reason": "expand_or_restructure_content"})
        plan.append({"agent": "seo_agent", "reason": "repair_title_description_keyword_structure"})
    if int(card.get("evidence", 0)) < 7:
        plan.append({"agent": "analytics_agent", "reason": "attach_evidence_or_measurement_basis"})
    if int(card.get("compliance", 0)) < 7:
        plan.append({"agent": "legal_agent", "reason": "review_policy_and_disclosure"})
        plan.append({"agent": "risk_agent", "reason": "assess_platform_or_claim_risk"})
    if int(card.get("readiness", 0)) < 7:
        plan.append({"agent": "publisher_agent", "reason": "reload_and_editor_state_verification"})
    return plan
