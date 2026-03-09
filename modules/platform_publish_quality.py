"""Strict platform-specific publish quality gates.

Fail closed: partial draft/create results must not be treated as done unless
the platform returns enough proof that the required artifacts actually landed.
"""

from __future__ import annotations

from typing import Any


def _nested(payload: dict[str, Any], dotted: str) -> Any:
    cur: Any = payload
    for part in str(dotted or "").split("."):
        if not part:
            continue
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _truthy(result: dict[str, Any], *paths: str) -> bool:
    for path in paths:
        val = _nested(result, path)
        if isinstance(val, bool) and val:
            return True
        if isinstance(val, (int, float)) and float(val) > 0:
            return True
        if isinstance(val, str) and val.strip():
            return True
        if isinstance(val, list) and len(val) > 0:
            return True
    return False


def _strs(result: dict[str, Any], *paths: str) -> list[str]:
    out: list[str] = []
    for path in paths:
        val = _nested(result, path)
        if isinstance(val, str) and val.strip():
            out.append(val.strip())
        elif isinstance(val, list):
            out.extend([str(x).strip() for x in val if str(x).strip()])
    return out


def validate_platform_publish_quality(platform: str, result: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, list[str]]:
    p = str(platform or result.get("platform") or "").strip().lower()
    if not isinstance(result, dict):
        return False, ["result_not_dict"]
    status = str(result.get("status") or "").strip().lower()
    if status not in {"draft", "created", "published", "success", "completed", "ok", "prepared"}:
        return True, []

    errors: list[str] = []
    payload = payload or {}

    if p == "etsy":
        if not _truthy(result, "listing_id", "id"):
            errors.append("etsy_missing_listing_id")
        if not _truthy(result, "screenshot_path", "evidence.screenshot"):
            errors.append("etsy_missing_screenshot")
        wants_file = bool(str(payload.get("pdf_path") or payload.get("file_path") or "").strip())
        wants_images = any(
            str(payload.get(k) or "").strip()
            for k in ("cover_path", "image_path", "thumb_path", "preview_path", "gallery_path")
        ) or bool(payload.get("preview_paths"))
        if wants_file:
            if not (
                _truthy(result, "file_attached", "has_pdf_name", "audit.hasPdfName", "editor_audit.hasPdfName")
                or not _truthy(result, "audit.hasUploadPrompt", "editor_audit.hasUploadPrompt")
            ):
                errors.append("etsy_file_not_confirmed")
        if wants_images and not _truthy(result, "image_count", "audit.image_count", "editor_audit.image_count"):
            errors.append("etsy_images_not_confirmed")
        if payload.get("tags") and not _truthy(result, "tags_confirmed", "audit.hasTags", "editor_audit.hasTags"):
            errors.append("etsy_tags_not_confirmed")
        if payload.get("materials") and not _truthy(result, "materials_confirmed", "audit.hasMaterials", "editor_audit.hasMaterials"):
            errors.append("etsy_materials_not_confirmed")
        if str(result.get("error") or "").strip():
            errors.append("etsy_result_contains_error")

    elif p == "gumroad":
        wants_file = bool(str(payload.get("pdf_path") or payload.get("file_path") or "").strip())
        wants_images = any(
            str(payload.get(k) or "").strip()
            for k in ("cover_path", "thumb_path", "image_path", "preview_path")
        ) or bool(payload.get("preview_paths"))
        attached = [x.lower() for x in _strs(result, "files_attached")]
        if wants_file and not (_truthy(result, "main_file_attached") or any(x.endswith(".pdf") for x in attached)):
            errors.append("gumroad_main_file_not_confirmed")
        if wants_images and not (
            _truthy(result, "cover_confirmed", "preview_confirmed", "thumbnail_confirmed", "image_count")
            or any(x.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) for x in attached)
        ):
            errors.append("gumroad_visuals_not_confirmed")
        if payload.get("tags") and not _truthy(result, "tags_confirmed"):
            if str(result.get("error") or "").strip() == "tags_not_set":
                errors.append("gumroad_tags_not_confirmed")
        if not _truthy(result, "draft_confirmed") and status == "draft":
            errors.append("gumroad_draft_not_confirmed")
        if str(result.get("error") or "").strip():
            errors.append("gumroad_result_contains_error")

    elif p == "amazon_kdp":
        if not _truthy(result, "screenshot_path", "evidence.screenshot"):
            errors.append("kdp_missing_screenshot")
        if not _truthy(result, "output.fields_filled"):
            errors.append("kdp_fields_not_confirmed")
        if str(payload.get("manuscript_path") or "").strip() and not _truthy(result, "output.manuscript_uploaded"):
            errors.append("kdp_manuscript_not_confirmed")
        if str(payload.get("cover_path") or "").strip() and not _truthy(result, "output.cover_uploaded"):
            errors.append("kdp_cover_not_confirmed")

    elif p == "printful":
        wants_sync = isinstance(payload.get("sync_product"), dict)
        if wants_sync and not (_truthy(result, "template_id", "id") or _truthy(result, "etsy_edit_url")):
            errors.append("printful_sync_not_confirmed")

    elif p == "kofi":
        if status in {"created", "published"} and not _truthy(result, "url"):
            errors.append("kofi_missing_public_url")

    elif p in {"twitter", "x", "pinterest", "reddit"}:
        if status in {"created", "published"} and not _truthy(result, "url"):
            errors.append(f"{p}_missing_public_url")

    return len(errors) == 0, errors
