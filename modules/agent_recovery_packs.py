"""Recovery packs for weakest agents after Phase I-N completion."""

from __future__ import annotations

from typing import Any

_RECOVERY_PACKS: dict[str, dict[str, Any]] = {
    "browser_agent": {
        "family": "commerce_execution",
        "failure_signatures": [
            "auth_interrupt",
            "challenge_detected",
            "timeout",
            "target_closed",
            "profile_completion_required",
        ],
        "preferred_actions": [
            "capture_screenshot",
            "reload_and_reprobe",
            "switch_to_screenshot_first",
            "request_otp_via_account_manager",
            "escalate_profile_completion",
        ],
    },
    "translation_agent": {
        "family": "content_growth",
        "failure_signatures": [
            "provider_empty_response",
            "language_detection_uncertain",
            "cache_miss_loop",
            "inconsistent_translation",
        ],
        "preferred_actions": [
            "fallback_language_detect",
            "retry_with_provider_route",
            "apply_local_consistency_check",
            "cache_verified_result",
        ],
    },
    "economics_agent": {
        "family": "content_growth",
        "failure_signatures": [
            "missing_competitor_signal",
            "weak_margin_basis",
            "no_price_anchor",
        ],
        "preferred_actions": [
            "request_analytics_snapshot",
            "request_research_market_scan",
            "switch_to_conservative_pricing_mode",
        ],
    },
    "account_manager": {
        "family": "commerce_execution",
        "failure_signatures": [
            "auth_state_unknown",
            "otp_required",
            "session_expired",
            "platform_limit_hit",
        ],
        "preferred_actions": [
            "refresh_session_state",
            "request_owner_otp",
            "handoff_to_browser_agent",
            "mark_platform_temporarily_blocked",
        ],
    },
    "legal_agent": {
        "family": "governance_resilience",
        "failure_signatures": [
            "policy_basis_missing",
            "tos_uncertain",
            "copyright_risk_unclear",
        ],
        "preferred_actions": [
            "load_platform_policy_pack",
            "request_risk_review",
            "block_publish_until_basis_found",
        ],
    },
    "content_creator": {
        "family": "content_growth",
        "failure_signatures": [
            "missing_asset_manifest",
            "weak_platform_fit",
            "quality_reject",
            "copy_too_generic",
        ],
        "preferred_actions": [
            "reload_content_patterns",
            "request_seo_pack_refresh",
            "request_marketing_angle_refresh",
            "generate_replacement_assets",
            "rebuild_asset_manifest",
            "run_quality_self_check",
        ],
    },
    "marketing_agent": {
        "family": "content_growth",
        "failure_signatures": [
            "unclear_audience",
            "no_budget_fit",
            "weak_offer_angle",
            "strategy_conflict",
        ],
        "preferred_actions": [
            "request_research_refresh",
            "request_analytics_snapshot",
            "switch_to_conservative_gtm_mode",
            "escalate_positioning_review",
            "rebuild_test_matrix",
            "resegment_target_audience",
        ],
    },
    "trend_scout": {
        "family": "intelligence_research",
        "failure_signatures": [
            "source_drought",
            "only_fallback_sources",
            "conflicting_signal_direction",
            "weak_trend_confidence",
        ],
        "preferred_actions": [
            "reload_signal_sources",
            "request_research_validation",
            "request_marketing_context",
            "fallback_to_multi_source_scan",
            "build_signal_matrix",
            "tighten_confidence_thresholds",
        ],
    },
    "email_agent": {
        "family": "content_growth",
        "failure_signatures": [
            "missing_audience",
            "sequence_gap",
            "send_blocker",
            "weak_subject_line",
        ],
        "preferred_actions": [
            "load_email_templates",
            "request_marketing_pack",
            "request_analytics_baseline",
            "switch_to_draft_only_mode",
            "run_deliverability_checklist",
            "rebuild_sequence_summary",
        ],
    },
    "research_agent": {
        "family": "intelligence_research",
        "failure_signatures": [
            "weak_source_mix",
            "gap_count_high",
            "judge_reject",
            "comparison_missing",
        ],
        "preferred_actions": [
            "expand_source_mix",
            "request_trend_validation",
            "request_document_ingest",
            "rerun_judge_stage",
            "rebuild_source_coverage_map",
            "compress_findings_into_operator_pack",
        ],
    },
    "document_agent": {
        "family": "intelligence_research",
        "failure_signatures": [
            "unsupported_format",
            "missing_source_file",
            "ocr_unavailable",
            "extract_quality_low",
        ],
        "preferred_actions": [
            "switch_parser",
            "fallback_to_ocr",
            "request_source_retry",
            "escalate_ingest_review",
            "build_review_checklist",
            "repackage_extracted_manifest",
        ],
    },
}


def get_agent_recovery_pack(agent_name: str) -> dict[str, Any]:
    return dict(_RECOVERY_PACKS.get(str(agent_name or "").strip(), {}))
