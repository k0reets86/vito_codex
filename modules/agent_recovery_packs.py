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
}


def get_agent_recovery_pack(agent_name: str) -> dict[str, Any]:
    return dict(_RECOVERY_PACKS.get(str(agent_name or "").strip(), {}))
