"""Runtime helpers for growth/content family agents."""

from __future__ import annotations

from typing import Any


def build_marketing_runtime_profile(product: str, audience: str, budget_usd: float) -> dict[str, Any]:
    budget = max(float(budget_usd or 0), 0.0)
    if budget < 100:
        profile = "lean"
        next_actions = ["focus_on_organic_distribution", "validate_offer_angle", "collect_first_signals"]
    elif budget < 1000:
        profile = "test_and_scale"
        next_actions = ["launch_channel_tests", "measure_ctr_and_cac", "cut_weak_creatives"]
    else:
        profile = "growth"
        next_actions = ["split_budget_by_channel", "add_retention_loop", "expand_affiliate_layer"]
    return {
        "product": str(product or "").strip(),
        "target_audience": str(audience or "").strip(),
        "budget_usd": budget,
        "budget_profile": profile,
        "next_actions": next_actions,
    }


def build_risk_runtime_profile(action: str, risk_level: str, factors: list[str] | None) -> dict[str, Any]:
    level = str(risk_level or "").strip().lower() or "unknown"
    risks = [str(x).strip() for x in (factors or []) if str(x).strip()]
    blocked = level == "high" or "anti_abuse_risk" in risks
    return {
        "action": str(action or "").strip(),
        "risk_level": level,
        "risk_factors": risks,
        "block_recommended": blocked,
        "next_actions": (
            ["request_legal_review", "reduce_automation", "change_distribution_path"]
            if blocked
            else ["proceed_with_verifier", "monitor_platform_feedback", "log_risk_decision"]
        ),
    }


def build_email_runtime_profile(topic: str, audience: str, email_count: int | None = None) -> dict[str, Any]:
    audience_text = str(audience or "").strip() or "subscribers"
    count = max(int(email_count or 0), 0)
    mode = "sequence" if count else "single_send"
    return {
        "topic": str(topic or "").strip(),
        "audience": audience_text,
        "mode": mode,
        "email_count": count,
        "next_actions": (
            ["draft_sequence", "schedule_send", "track_open_and_click"]
            if count
            else ["review_subject", "send_test_email", "schedule_send"]
        ),
    }


def build_partnership_runtime_profile(niche: str, candidates: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = list(candidates or [])
    scored = []
    for row in rows:
        fit = str(row.get("fit") or "").lower()
        commission = str(row.get("commission") or "").replace("%", "").strip()
        try:
            commission_score = float(commission) / 10.0
        except Exception:
            commission_score = 1.0
        fit_bonus = 1.5 if any(x in fit for x in ("creator", "newsletter", "education")) else 0.5
        row = dict(row)
        row["partner_score"] = round(min(10.0, commission_score + fit_bonus), 2)
        scored.append(row)
    scored.sort(key=lambda item: item.get("partner_score", 0), reverse=True)
    return {
        "niche": str(niche or "").strip(),
        "candidate_count": len(scored),
        "top_candidates": scored[:3],
        "next_actions": ["shortlist_top_candidates", "prepare_outreach", "match_offer_to_partner_audience"],
    }

