"""Platform auth/account remediation packs for AccountManager."""

from __future__ import annotations

from typing import Any


def build_platform_auth_pack(platform: str) -> dict[str, Any]:
    key = str(platform or "").strip().lower()
    common = {
        "otp_flow": True,
        "profile_completion_possible": True,
        "session_refresh_possible": True,
    }
    per = {
        "etsy": {"checkpoints": ["shop_manager", "draft_editor", "photo_upload"], "known_gates": ["what_is_this_item", "photo_required"]},
        "gumroad": {"checkpoints": ["product_editor", "content_upload", "share_tab"], "known_gates": ["daily_product_limit", "save_route_failure"]},
        "amazon_kdp": {"checkpoints": ["bookshelf", "details", "content", "pricing"], "known_gates": ["mfa", "account_information", "processing_delay"]},
        "kofi": {"checkpoints": ["shop_settings", "product_editor"], "known_gates": ["cloudflare_challenge"]},
        "reddit": {"checkpoints": ["subreddit_submit", "flair"], "known_gates": ["anti_spam", "community_rules"]},
    }
    out = dict(common)
    out.update(per.get(key, {"checkpoints": [], "known_gates": []}))
    out["platform"] = key
    return out


def build_auth_remediation(platform: str, error: str = "", configured: bool | None = None) -> dict[str, Any]:
    err = str(error or "")
    low = err.lower()
    pack = build_platform_auth_pack(platform)
    state = "configured" if configured else "missing_credentials"
    next_actions: list[str] = []
    if "application-specific password required" in low:
        state = "app_password_required"
        next_actions = ["create_app_password", "retry_email_code_fetch"]
    elif "code_not_found" in low:
        state = "verification_code_missing"
        next_actions = ["wait_and_retry_inbox", "handoff_to_browser_agent"]
    elif "otp" in low or "mfa" in low:
        state = "otp_required"
        next_actions = ["request_owner_otp", "resume_auth_flow"]
    elif "cloudflare" in low:
        state = "anti_bot_gate"
        next_actions = ["switch_to_screenshot_first", "manual_browser_pause"]
    elif configured:
        next_actions = ["session_health_check", "profile_completion_check"]
    else:
        next_actions = ["set_credentials", "profile_completion_check"]
    return {
        "platform": str(platform or "").strip().lower(),
        "auth_state": state,
        "auth_pack": pack,
        "error": err[:240],
        "next_actions": next_actions,
        "escalation_target": "browser_agent" if "browser" in " ".join(next_actions) or "profile" in " ".join(next_actions) else "owner",
    }
