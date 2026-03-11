"""Runtime helpers for weakest-agent uplift."""
from __future__ import annotations
from typing import Any


def translation_recovery_hints(quality_checks: list[dict[str, Any]], risk_flags: list[str] | None=None) -> list[str]:
    hints=[]
    failed=[c.get('name') for c in quality_checks if not c.get('ok')]
    if 'non_empty' in failed:
        hints.append('retry_with_provider_route')
    if 'glossary_terms_preserved' in failed:
        hints.append('force_glossary_preservation')
    if 'length_ratio_reasonable' in failed:
        hints.append('compare_with_local_fallback')
    if risk_flags:
        hints.append('request_quality_judge_review')
    return hints or ['cache_verified_result','handoff_to_content_creator']


def economics_recovery_hints(output: dict[str, Any]) -> list[str]:
    hints=[]
    conf=float(((output.get('pricing_confidence') or {}).get('confidence_score') or 0.0))
    if conf < 0.75:
        hints.append('request_research_market_scan')
    if output.get('contribution_margin', 1) <= 0:
        hints.append('switch_to_conservative_pricing_mode')
    if output.get('breakeven_units_1000usd_fixed_cost', 1) > 80:
        hints.append('reduce_cac_or_raise_price')
    return hints or ['handoff_to_ecommerce_agent','track_real_conversion']


def partnership_recovery_hints(profile: dict[str, Any]) -> list[str]:
    count=int(profile.get('candidate_count') or 0)
    if count < 2:
        return ['expand_partner_search','request_marketing_audience_map','retry_with_adjacent_niche']
    return ['personalize_outreach','validate_offer_match','track_reply_rate']


def devops_repair_confidence(success: bool, issue_count: int, can_auto_remediate: bool) -> dict[str, Any]:
    score=0.55
    if success:
        score += 0.25
    if issue_count == 0:
        score += 0.1
    if can_auto_remediate:
        score += 0.1
    return {'repair_confidence': round(min(score,0.95),2), 'verification_required': not success or issue_count>0}


def analytics_recovery_hints(output: dict[str, Any], metadata: dict[str, Any] | None=None) -> list[str]:
    anomalies=list(output.get('anomalies') or [])
    confidence=str(((metadata or {}).get('analytics_runtime_profile') or {}).get('forecast_confidence') or '')
    if anomalies:
        return ['open_investigation','escalate_to_marketing_and_ecommerce','compare_against_baseline']
    if confidence in {'low','unknown'}:
        return ['request_research_refresh','request_benchmark_refresh','reduce_forecast_confidence_in_reporting']
    return ['monitor_next_period','handoff_optimization_recommendations']
