from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from modules.platform_target_registry import (
    load_protected_platform_targets,
    load_working_platform_targets,
    protect_platform_target,
    save_working_platform_targets,
    target_identity,
)


def platform_working_target(platform: str) -> dict[str, Any]:
    p = str(platform or "").strip().lower()
    out = dict((load_working_platform_targets().get(p) or {}))
    if out:
        out.setdefault("platform", p)
    return out


def is_target_protected(platform: str, current: dict[str, Any]) -> bool:
    p = str(platform or "").strip().lower()
    if not p or not isinstance(current, dict) or not current:
        return False
    cur = target_identity(current)
    if not cur:
        return False
    protected = load_protected_platform_targets().get(p) or []
    for item in protected:
        if not isinstance(item, dict):
            continue
        ref = target_identity(item)
        if not ref:
            continue
        for key in ("id", "target_slug", "target_listing_id", "target_document_id", "target_product_id", "url"):
            if cur.get(key) and ref.get(key) and cur.get(key) == ref.get(key):
                return True
    return False


def working_target_matches_task(current: dict[str, Any], task_root_id: str) -> bool:
    if not isinstance(current, dict) or not current:
        return False
    current_task_root = str(current.get("task_root_id") or "").strip()
    target_id = str(
        current.get("id")
        or current.get("target_slug")
        or current.get("target_listing_id")
        or current.get("target_document_id")
        or current.get("target_product_id")
        or ""
    ).strip()
    if not target_id or not bool(current.get("mutable", True)) or not current_task_root:
        return False
    if is_target_protected(str(current.get("platform") or current.get("_platform") or ""), current):
        return False
    return bool(task_root_id) and current_task_root == str(task_root_id).strip()


def remember_platform_working_target(platform: str, result: dict[str, Any]) -> None:
    p = str(platform or "").strip().lower()
    if not p or not isinstance(result, dict):
        return
    targets = load_working_platform_targets()
    current = dict(targets.get(p) or {})
    rid = str(
        result.get("listing_id")
        or result.get("product_id")
        or result.get("target_product_id")
        or result.get("post_id")
        or result.get("document_id")
        or result.get("target_document_id")
        or result.get("book_id")
        or result.get("id")
        or ""
    ).strip()
    url = str(result.get("url") or "").strip()
    if p == "gumroad":
        slug = str(result.get("slug") or "").strip()
        if not slug and url:
            m = re.search(r"gumroad\.com/l/([A-Za-z0-9_-]+)", url)
            if m:
                slug = m.group(1)
        if slug:
            current["target_slug"] = slug
    elif p == "etsy" and rid:
        current["target_listing_id"] = rid
    elif p == "amazon_kdp" and rid:
        current["target_document_id"] = rid
    elif p in {"kofi", "printful"} and rid:
        current["target_product_id"] = rid
    incoming_target = {
        "id": rid,
        "url": url,
        "target_slug": current.get("target_slug"),
        "target_listing_id": current.get("target_listing_id"),
        "target_document_id": current.get("target_document_id"),
        "target_product_id": current.get("target_product_id"),
    }
    if is_target_protected(p, current) and target_identity(current) != target_identity(incoming_target):
        return
    if rid:
        current["id"] = rid
    if url:
        current["url"] = url
    current["platform"] = p
    task_root_id = str(
        result.get("task_root_id")
        or result.get("project_id")
        or result.get("listing_work_id")
        or result.get("publish_work_id")
        or ""
    ).strip()
    if task_root_id:
        current["task_root_id"] = task_root_id
    status = str(result.get("status") or "").strip().lower()
    is_published = bool(result.get("is_published")) or status == "published"
    if "draft_confirmed" in result:
        current["draft_confirmed"] = bool(result.get("draft_confirmed"))
    current["mutable"] = not is_published
    current["locked"] = bool(is_published)
    if is_published:
        current["locked_reason"] = "published_requires_explicit_target"
        protect_platform_target(p, current, reason="published_requires_explicit_target")
    current["status"] = status or current.get("status", "")
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    targets[p] = current
    save_working_platform_targets(targets)
