"""Runtime helpers for autonomy/self-evolution lanes."""

from __future__ import annotations

from collections import Counter
from typing import Any


def score_improvement_proposal(
    *,
    issue_buckets: Counter | dict[str, int] | None,
    owner_alignment: bool,
    skill_count: int,
    title: str,
) -> dict[str, Any]:
    buckets = Counter(issue_buckets or {})
    top_bucket, top_count = ("general", 0)
    if buckets:
        top_bucket, top_count = buckets.most_common(1)[0]
    score = 5.5
    if top_count >= 3:
        score += 1.0
    if owner_alignment:
        score += 1.0
    if skill_count >= 10:
        score += 0.5
    lane = "runtime_hardening"
    title_low = str(title or "").lower()
    if "skill" in title_low:
        lane = "skill_growth"
    elif "owner" in title_low:
        lane = "owner_alignment"
    elif "failure" in title_low or "fix" in title_low:
        lane = "repair"
    return {
        "proposal_score": round(min(score, 9.5), 2),
        "dominant_issue_bucket": top_bucket,
        "issue_bucket_count": int(top_count),
        "execution_lane": lane,
        "approval_mode": "owner_review" if lane in {"owner_alignment", "repair"} else "safe_auto_candidate",
    }


def build_self_evolve_runtime_profile(
    *,
    proposal_count: int,
    issue_buckets: Counter | dict[str, int] | None,
    owner_alignment: bool,
) -> dict[str, Any]:
    buckets = Counter(issue_buckets or {})
    return {
        "proposal_count": int(proposal_count or 0),
        "issue_buckets": dict(buckets),
        "owner_alignment": bool(owner_alignment),
        "recovery_mode": "needs_issue_density" if not buckets else "proposal_ready",
        "next_actions": (
            ["collect_more_reflections", "wait_for_next_cycle", "avoid_forced_improvement"]
            if not buckets
            else ["rank_proposals", "send_to_owner", "attach_verified_followups"]
        ),
    }
