"""Browser recovery and selectorless preflight decisions."""

from __future__ import annotations

from typing import Any


def looks_like_selector(key: str) -> bool:
    text = str(key or "").strip()
    return any(ch in text for ch in "#.[>:=@") or text.startswith(("input", "textarea", "select", "//"))


def build_form_fill_preflight(data: dict[str, Any]) -> dict[str, Any]:
    fields = dict(data or {})
    selector_keys = [k for k in fields if looks_like_selector(k)]
    generic_keys = [k for k in fields if k not in selector_keys]
    return {
        "selector_keys": selector_keys,
        "generic_keys": generic_keys,
        "selector_mapping_required": bool(generic_keys and not selector_keys),
        "next_actions": ["map_generic_fields_to_selectors", "capture_page_form_schema"] if generic_keys and not selector_keys else [],
    }


_SERVICE_RECOVERY_ACTIONS: dict[str, list[str]] = {
    "etsy": ["reload_listing_editor", "recheck_digital_type", "verify_file_and_images", "retry_save_as_draft"],
    "gumroad": ["reload_product_editor", "verify_content_pdf", "verify_cover_slot", "retry_save_and_continue"],
    "amazon_kdp": ["resume_existing_draft", "reopen_content_or_pricing", "recheck_processing_status", "retry_after_kdp_processing"],
    "printful": ["reopen_product_editor", "verify_design_placement", "retry_save_template", "reopen_publish_wizard"],
    "kofi": ["reload_shop_settings", "verify_item_card", "reopen_share_link_modal", "retry_publish_after_settings_reload"],
    "reddit": ["reopen_submit_page", "recheck_rules_and_flair", "switch_to_community_first_posting", "lower_post_frequency"],
    "twitter": ["reopen_compose", "verify_media_attachment", "retry_post_after_profile_check"],
    "pinterest": ["reopen_pin_editor", "verify_title_description_link", "retry_publish_after_reload"],
}

_SERVICE_BLOCK_CONDITIONS: dict[str, list[str]] = {
    "etsy": ["auth_interrupt", "profile_completion_required", "challenge_detected"],
    "gumroad": ["auth_interrupt", "daily_product_limit", "challenge_detected"],
    "amazon_kdp": ["otp_required", "kdp_processing_pending", "profile_completion_required"],
    "printful": ["auth_interrupt", "store_connection_required", "challenge_detected"],
    "kofi": ["interactive_auth_required", "cloudflare_challenge", "payment_setup_required"],
    "reddit": ["anti_spam_reject", "account_reputation_gate", "community_rule_violation"],
    "twitter": ["auth_interrupt", "rate_limit", "media_processing_failed"],
    "pinterest": ["auth_interrupt", "profile_completion_required", "link_field_not_persisted"],
}


def build_browser_recovery(service: str, mode: str, reason: str) -> dict[str, Any]:
    svc = str(service or "").strip().lower()
    next_actions = list(_SERVICE_RECOVERY_ACTIONS.get(svc) or [])
    if reason == "selector_mapping_required":
        next_actions = ["capture_page_form_schema", "map_generic_fields_to_selectors"] + next_actions
    elif reason == "no_matching_selectors":
        next_actions = ["take_screenshot_and_dom_snapshot", "refresh_selector_map"] + next_actions
    elif reason == "auth_interrupt":
        next_actions = ["request_owner_auth", "resume_saved_session"] + next_actions
    elif reason == "profile_completion_required":
        next_actions = ["open_profile_completion_route", "fill_minimum_required_profile_fields"] + next_actions
    return {
        "service": svc,
        "mode": str(mode or "").strip().lower(),
        "reason": str(reason or "").strip(),
        "retry_strategy": "screenshot_first_retry",
        "escalation_path": ["account_manager", "quality_judge"],
        "block_conditions": list(_SERVICE_BLOCK_CONDITIONS.get(svc) or ["challenge_detected", "auth_interrupt", "profile_completion_required"]),
        "next_actions": next_actions,
    }
