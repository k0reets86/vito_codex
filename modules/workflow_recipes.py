"""Deterministic workflow recipes for core platform operations."""

from __future__ import annotations

from typing import Any


_RECIPES: dict[str, dict[str, Any]] = {
    "gumroad_publish": {
        "platform": "gumroad",
        "goal": "Create/update listing and publish with evidence.",
        "steps": [
            "auth_check",
            "prepare_listing_fields",
            "upload_assets",
            "seo_finalize",
            "save_draft",
            "publish",
            "verify_public_url",
        ],
        "required_evidence": ["url", "id"],
    },
    "etsy_publish": {
        "platform": "etsy",
        "goal": "Create/update Etsy listing in browser-safe mode.",
        "steps": [
            "auth_check",
            "open_listing_editor",
            "fill_required_fields",
            "attach_assets",
            "set_tags_category",
            "save_draft_or_publish",
            "verify_listing_url",
        ],
        "required_evidence": ["url"],
    },
    "kdp_publish": {
        "platform": "amazon_kdp",
        "goal": "Create/update KDP draft and verify bookshelf visibility.",
        "steps": [
            "auth_check",
            "open_bookshelf",
            "open_or_create_draft",
            "fill_book_metadata",
            "upload_manuscript_cover",
            "save_and_validate",
            "verify_bookshelf_entry",
        ],
        "required_evidence": [],
    },
    "kofi_publish": {
        "platform": "kofi",
        "goal": "Create/update Ko-fi product/post with profile consistency.",
        "steps": [
            "auth_check",
            "open_product_editor",
            "fill_title_description_price",
            "attach_image_or_file",
            "save_or_publish",
            "verify_page_url",
        ],
        "required_evidence": ["url"],
    },
    "twitter_publish": {
        "platform": "twitter",
        "goal": "Publish post/tweet and verify url.",
        "steps": [
            "auth_check",
            "compose_message",
            "attach_media_optional",
            "publish",
            "verify_post_url",
        ],
        "required_evidence": [],
    },
    "reddit_publish": {
        "platform": "reddit",
        "goal": "Publish subreddit post and verify permalink.",
        "steps": [
            "auth_check",
            "select_subreddit",
            "compose_title_body",
            "publish",
            "verify_permalink",
        ],
        "required_evidence": ["url"],
    },
    "pinterest_publish": {
        "platform": "pinterest",
        "goal": "Create or publish a Pinterest pin and verify resulting URL.",
        "steps": [
            "auth_check",
            "open_pin_editor",
            "fill_title_description_link",
            "attach_media_optional",
            "publish_or_save",
            "verify_pin_url",
        ],
        "required_evidence": ["url"],
    },
}


def list_workflow_recipes() -> list[dict[str, Any]]:
    out = []
    for key in sorted(_RECIPES.keys()):
        row = dict(_RECIPES[key])
        row["name"] = key
        out.append(row)
    return out


def get_workflow_recipe(name: str) -> dict[str, Any] | None:
    n = str(name or "").strip().lower()
    if not n:
        return None
    rec = _RECIPES.get(n)
    return dict(rec) if isinstance(rec, dict) else None


def platform_recipe(platform: str) -> dict[str, Any] | None:
    p = str(platform or "").strip().lower()
    for key, rec in _RECIPES.items():
        if str(rec.get("platform", "")).lower() == p:
            row = dict(rec)
            row["name"] = key
            return row
    return None
