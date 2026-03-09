"""Executable policy/TOS packs for LegalAgent."""

from __future__ import annotations

from typing import Any

POLICY_PACKS: dict[str, dict[str, Any]] = {
    "etsy": {
        "digital_goods_allowed": True,
        "main_checks": ["digital_download_type", "originality", "copyright_basis", "no forbidden claims"],
        "publish_blockers": ["infringing_brand_use", "misleading_income_claims"],
    },
    "gumroad": {
        "digital_goods_allowed": True,
        "main_checks": ["deliverable_present", "originality", "refund_risk", "no policy-violating promises"],
        "publish_blockers": ["stolen_content", "prohibited financial claims"],
    },
    "amazon_kdp": {
        "digital_goods_allowed": True,
        "main_checks": ["rights_confirmed", "public_domain_check", "cover/manuscript originality"],
        "publish_blockers": ["public_domain_without_transformation", "infringing_cover", "duplicate low-content abuse"],
    },
    "reddit": {
        "digital_goods_allowed": "community_dependent",
        "main_checks": ["subreddit_rules_read", "self_promo_ratio_ok", "flair_required", "non-spam positioning"],
        "publish_blockers": ["community_self_promo_ban", "spam repetition"],
    },
}


def get_policy_pack(platform: str) -> dict[str, Any]:
    key = str(platform or "").strip().lower()
    return dict(POLICY_PACKS.get(key, {
        "digital_goods_allowed": "unknown",
        "main_checks": ["platform_rules_read", "copyright_basis", "claim_review"],
        "publish_blockers": ["policy_basis_missing"],
    }))


def build_policy_basis(platform: str, content: str = "") -> dict[str, Any]:
    pack = get_policy_pack(platform)
    txt = str(content or "").lower()
    blockers = list(pack.get("publish_blockers") or [])
    issues: list[str] = []
    if any(k in txt for k in ("marvel", "disney", "star wars", "nintendo")):
        issues.append("brand_or_franchise_reference")
    if "guaranteed income" in txt or "guaranteed profit" in txt:
        issues.append("misleading_income_claim")
    decision = "review_required" if issues else "policy_basis_present"
    return {
        "platform": str(platform or "").strip().lower(),
        "policy_pack": pack,
        "issues": issues,
        "decision": decision,
        "block_publish": bool(issues),
        "basis_strength": "medium" if not issues else "weak",
        "blockers": blockers,
    }
