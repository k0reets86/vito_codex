"""Operational output packs for weak growth/research agents.

These helpers turn locally-generated outputs into richer runtime-ready packs:
- used skills
- evidence bundles
- next actions
- recovery hints
- quality checks
"""

from __future__ import annotations

from typing import Any


def _clean_list(items: list[Any] | None) -> list[str]:
    return [str(item).strip() for item in (items or []) if str(item).strip()]


def build_content_operational_pack(
    *,
    topic: str,
    platform: str,
    asset_paths: list[str] | None,
    seo_score: float | int | None = None,
    publish_ready: bool | None = None,
    tags: list[str] | None = None,
    category: str = "",
) -> dict[str, Any]:
    assets = _clean_list(asset_paths)
    skill_names = [
        "asset_manifest_assembly",
        "platform_fit_copy_packaging",
        "listing_seo_alignment",
        "content_quality_self_check",
    ]
    return {
        "used_skills": skill_names,
        "evidence": {
            "topic": str(topic or "").strip(),
            "platform": str(platform or "").strip(),
            "asset_count": len(assets),
            "asset_paths": assets[:8],
            "seo_score": float(seo_score or 0.0),
            "publish_ready": bool(publish_ready),
            "tags": _clean_list(tags)[:12],
            "category": str(category or "").strip(),
        },
        "quality_checks": [
            "title_present",
            "description_present",
            "asset_manifest_present",
            "platform_specific_tags_present",
        ],
        "next_actions": (
            ["attach_assets_to_listing", "run_quality_review", "handoff_to_ecommerce_agent"]
            if assets
            else ["generate_assets", "refresh_listing_copy", "rerun_platform_fit_review"]
        ),
        "recovery_hints": (
            ["generate_missing_preview_assets", "request_seo_pack_refresh", "rerun_quality_review"]
            if not assets
            else ["rerun_platform_fit_review", "refresh_tags_and_category_if_rejected"]
        ),
    }


def build_marketing_operational_pack(
    *,
    product: str,
    audience: str,
    budget_usd: float,
    channels: list[dict[str, Any]] | None,
    timeline: list[str] | None,
) -> dict[str, Any]:
    rows = list(channels or [])
    strongest = rows[0] if rows else {}
    return {
        "used_skills": [
            "offer_angle_selection",
            "channel_mix_planning",
            "budget_fit_strategy",
            "timeline_execution_mapping",
        ],
        "evidence": {
            "product": str(product or "").strip(),
            "audience": str(audience or "").strip(),
            "budget_usd": max(float(budget_usd or 0.0), 0.0),
            "channel_count": len(rows),
            "primary_channel": str(strongest.get("channel") or "").strip(),
            "timeline_length": len(list(timeline or [])),
        },
        "next_actions": [
            "request_creative_pack",
            "request_seo_alignment",
            "request_analytics_baseline",
            "launch_small_channel_test",
        ],
        "recovery_hints": [
            "switch_to_conservative_gtm_mode",
            "request_research_refresh_if_audience_unclear",
            "rebuild_channel_mix_if_budget_profile_changes",
        ],
        "quality_checks": [
            "audience_defined",
            "offer_angle_defined",
            "channel_mix_defined",
            "timeline_defined",
        ],
    }


def build_trend_operational_pack(
    *,
    mode: str,
    source_urls: list[str] | None,
    fallback_reason: str = "",
    summary_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = list(summary_items or [])
    return {
        "used_skills": [
            "multi_source_signal_collection",
            "trend_direction_ranking",
            "fallback_signal_recovery",
            "niche_seed_generation",
        ],
        "evidence": {
            "mode": str(mode or "").strip(),
            "source_count": len(_clean_list(source_urls)),
            "fallback_reason": str(fallback_reason or "").strip(),
            "summary_items": items[:6],
        },
        "next_actions": [
            "handoff_top_signals_to_research_agent",
            "compare_signal_direction",
            "generate_niche_candidates",
        ],
        "recovery_hints": (
            ["restore_primary_sources", "rerun_trend_scan", "compare_fallback_vs_primary"]
            if fallback_reason
            else ["request_research_validation_if_signal_conflicts"]
        ),
        "quality_checks": [
            "at_least_one_signal_source",
            "direction_or_fallback_present",
            "niche_seed_ready",
        ],
    }


def build_email_operational_pack(
    *,
    topic: str,
    audience: str,
    mode: str,
    email_count: int,
    subject: str = "",
    cta: str = "",
) -> dict[str, Any]:
    return {
        "used_skills": [
            "subject_line_packaging",
            "audience_alignment",
            "sequence_cadence_planning",
            "send_readiness_checks",
        ],
        "evidence": {
            "topic": str(topic or "").strip(),
            "audience": str(audience or "").strip(),
            "mode": str(mode or "").strip(),
            "email_count": max(int(email_count or 0), 0),
            "subject": str(subject or "").strip(),
            "cta": str(cta or "").strip(),
        },
        "next_actions": (
            ["review_subject", "send_test_email", "schedule_send"]
            if str(mode or "").strip() != "sequence"
            else ["review_sequence_gaps", "schedule_sequence", "track_open_and_click"]
        ),
        "recovery_hints": [
            "request_marketing_pack_if_audience_unclear",
            "switch_to_draft_only_mode_if_send_blocked",
            "rewrite_subject_if_engagement_risk_high",
        ],
        "quality_checks": [
            "subject_present",
            "cta_present",
            "audience_defined",
        ],
    }


def build_document_operational_pack(
    *,
    path: str,
    capability: str,
    source_exists: bool,
    extracted_kind: str,
) -> dict[str, Any]:
    return {
        "used_skills": [
            "source_integrity_check",
            "parser_selection",
            "knowledge_capture",
            "extract_quality_review",
        ],
        "evidence": {
            "path": str(path or "").strip(),
            "capability": str(capability or "").strip(),
            "source_exists": bool(source_exists),
            "extracted_kind": str(extracted_kind or "").strip(),
        },
        "next_actions": (
            ["parse_document", "store_extract", "handoff_to_research_agent"]
            if source_exists
            else ["request_source_retry", "choose_supported_format", "retry_parse"]
        ),
        "recovery_hints": [
            "fallback_to_ocr_if_parser_unsupported",
            "switch_parser_if_extract_quality_low",
            "escalate_ingest_review_if_source_corrupt",
        ],
        "quality_checks": [
            "source_exists" if source_exists else "source_missing_detected",
            "extract_kind_set",
        ],
    }


def build_research_operational_pack(
    *,
    topic: str,
    sources: list[str] | None,
    overall_score: int | float | None,
    recommended_product: dict[str, Any] | None,
    report_path: str,
) -> dict[str, Any]:
    rec = dict(recommended_product or {})
    return {
        "used_skills": [
            "iterative_source_mixing",
            "evidence_grounded_synthesis",
            "opportunity_scoring",
            "operator_ready_recommendation",
        ],
        "evidence": {
            "topic": str(topic or "").strip(),
            "source_count": len(_clean_list(sources)),
            "sources": _clean_list(sources)[:8],
            "overall_score": int(overall_score or 0),
            "recommended_title": str(rec.get("title") or "").strip(),
            "recommended_platform": str(rec.get("platform") or "").strip(),
            "report_path": str(report_path or "").strip(),
        },
        "next_actions": [
            "handoff_recommended_product_to_marketing",
            "handoff_recommended_product_to_ecommerce",
            "persist_runbook_candidate",
        ],
        "recovery_hints": [
            "expand_source_mix_if_confidence_low",
            "rerun_judge_if_gaps_present",
            "request_document_ingest_if_evidence_weak",
        ],
        "quality_checks": [
            "report_path_present",
            "recommended_product_present",
            "overall_score_present",
        ],
    }
