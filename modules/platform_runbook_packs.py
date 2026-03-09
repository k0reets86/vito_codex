from __future__ import annotations

from typing import Any

from modules.platform_knowledge import get_service_knowledge


RUNBOOK_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "etsy": {
        "required_artifacts": ["title", "description", "price", "category", "tags", "main_file", "images"],
        "verify_points": ["editor_reload", "file_attached", "image_count", "tags_confirmed", "materials_confirmed"],
        "preferred_actions": ["create_once", "fill_details", "attach_file", "attach_images", "reload_verify"],
    },
    "gumroad": {
        "required_artifacts": ["title", "summary", "description", "category", "tags", "main_file", "cover", "thumbnail", "preview_gallery"],
        "verify_points": ["draft_confirmed", "main_file_attached", "cover_confirmed", "preview_confirmed", "thumbnail_confirmed", "public_page"],
        "preferred_actions": ["create_once", "content_pdf", "cover_upload", "thumbnail_upload", "save_and_continue", "reload_verify"],
    },
    "amazon_kdp": {
        "required_artifacts": ["details", "description", "keywords", "categories", "manuscript", "cover", "pricing"],
        "verify_points": ["bookshelf", "content_reload", "manuscript_uploaded", "cover_uploaded", "pricing_persisted"],
        "preferred_actions": ["resume_existing", "fill_details", "upload_content", "save_draft", "pricing_reload_verify"],
    },
    "printful": {
        "required_artifacts": ["design_file", "template", "mockups", "details", "sync_target"],
        "verify_points": ["template_saved", "publish_wizard", "etsy_edit_url"],
        "preferred_actions": ["open_product_page", "upload_design", "apply_design", "save_template", "publish_to_etsy"],
    },
    "kofi": {
        "required_artifacts": ["title", "description", "price", "file_or_link"],
        "verify_points": ["shop_settings_reload", "public_product_url"],
        "preferred_actions": ["authenticate", "open_shop_settings", "fill_product", "save_verify"],
    },
    "twitter": {
        "required_artifacts": ["text", "media_or_link"],
        "verify_points": ["permalink"],
        "preferred_actions": ["compose", "post", "verify_permalink"],
    },
    "pinterest": {
        "required_artifacts": ["title", "description", "image", "link"],
        "verify_points": ["pin_page", "description", "outbound_link"],
        "preferred_actions": ["create_pin", "fill_fields", "publish", "verify_pin_page"],
    },
    "reddit": {
        "required_artifacts": ["community", "title", "body_or_link", "image_optional", "flair_if_required"],
        "verify_points": ["submit_result", "post_url"],
        "preferred_actions": ["read_rules", "open_submit", "fill_form", "submit", "verify_post"],
    },
}


def _service_alias(service: str) -> str:
    low = str(service or "").strip().lower()
    aliases = {
        "amazon": "amazon_kdp",
        "kdp": "amazon_kdp",
        "x": "twitter",
        "ko-fi": "kofi",
    }
    return aliases.get(low, low)


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_service_runbook_pack(service: str) -> dict[str, Any]:
    svc = _service_alias(service)
    knowledge = get_service_knowledge(svc)
    base = RUNBOOK_REQUIREMENTS.get(svc, {})
    success_rows = list((knowledge.get("success_runbooks") or [])[-5:])
    failure_rows = list((knowledge.get("failure_runbooks") or [])[-5:])

    lessons: list[str] = []
    anti_patterns: list[str] = []
    evidence_keys: list[str] = []
    urls: list[str] = []
    for row in success_rows:
        lessons.extend([str(x) for x in (row.get("lessons") or [])])
        anti_patterns.extend([str(x) for x in (row.get("anti_patterns") or [])])
        urls.append(str(row.get("url") or "").strip())
        evidence = row.get("evidence") or {}
        if isinstance(evidence, dict):
            evidence_keys.extend([str(k) for k in evidence.keys()])
    for row in failure_rows:
        anti_patterns.extend([str(x) for x in (row.get("anti_patterns") or [])])
        evidence = row.get("evidence") or {}
        if isinstance(evidence, dict):
            evidence_keys.extend([str(k) for k in evidence.keys()])

    return {
        "service": svc,
        "required_artifacts": list(base.get("required_artifacts") or []),
        "verify_points": list(base.get("verify_points") or []),
        "preferred_actions": list(base.get("preferred_actions") or []),
        "recommended_steps": _dedupe_strings(lessons)[:20],
        "avoid_patterns": _dedupe_strings(anti_patterns)[:20],
        "evidence_keys_seen": _dedupe_strings(evidence_keys)[:20],
        "known_urls": _dedupe_strings(urls)[:10],
        "recent_success_count": len(success_rows),
        "recent_failure_count": len(failure_rows),
        "updated_at": str(knowledge.get("updated_at") or ""),
    }


def build_runbook_packs_for_services(services: list[str] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for service in services or []:
        svc = _service_alias(service)
        if not svc or svc in seen:
            continue
        seen.add(svc)
        out.append(build_service_runbook_pack(svc))
    return out
