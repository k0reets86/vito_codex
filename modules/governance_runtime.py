"""Runtime helpers for governance/resilience agents."""

from __future__ import annotations

from typing import Any


def build_legal_runtime_profile(
    *,
    platform: str,
    verdict: str,
    risk_score: int,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    issue_list = [str(x).strip() for x in (issues or []) if str(x).strip()]
    block_publish = str(verdict or "").strip().lower() in {"violation"} or int(risk_score or 0) >= 75
    return {
        "platform": str(platform or "").strip() or "generic",
        "verdict": str(verdict or "").strip() or "unknown",
        "risk_score": int(risk_score or 0),
        "issues": issue_list,
        "block_publish": block_publish,
        "required_reviewers": ["legal_agent", "risk_agent"] if block_publish else ["risk_agent"],
        "next_actions": (
            ["stop_release", "collect_policy_basis", "route_to_owner_for_decision"]
            if block_publish
            else ["log_basis", "continue_with_verifier", "monitor_moderation_feedback"]
        ),
    }


def build_hr_runtime_profile(
    *,
    weakest_agents: list[dict[str, Any]] | None,
    strongest_agents: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    low = list(weakest_agents or [])
    high = list(strongest_agents or [])
    return {
        "weakest_agents": low[:5],
        "strongest_agents": high[:5],
        "review_mode": "targeted_intervention" if low else "steady_improvement",
        "next_actions": (
            ["attach_recovery_pack", "open_benchmark_gap_review", "assign_dev_plan"]
            if low
            else ["continue_weekly_benchmarking", "promote_best_practices"]
        ),
    }


def build_partnership_execution_profile(
    *,
    niche: str,
    candidate_count: int,
    shortlist_count: int,
) -> dict[str, Any]:
    return {
        "niche": str(niche or "").strip(),
        "candidate_count": int(candidate_count or 0),
        "shortlist_count": int(shortlist_count or 0),
        "execution_mode": "outreach_ready" if shortlist_count else "research_only",
        "next_actions": (
            ["prepare_personalized_outreach", "attach_offer_fit_notes", "track_replies"]
            if shortlist_count
            else ["expand_candidate_pool", "improve_partner_fit_filter"]
        ),
    }
