import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT

_WORKING_PLATFORM_TARGETS = PROJECT_ROOT / "runtime" / "working_platform_targets.json"
_PROTECTED_PLATFORM_TARGETS = PROJECT_ROOT / "runtime" / "protected_platform_targets.json"


def load_working_platform_targets() -> dict[str, dict[str, Any]]:
    try:
        if not _WORKING_PLATFORM_TARGETS.exists():
            return {}
        data = json.loads(_WORKING_PLATFORM_TARGETS.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_working_platform_targets(data: dict[str, dict[str, Any]]) -> None:
    try:
        _WORKING_PLATFORM_TARGETS.parent.mkdir(parents=True, exist_ok=True)
        _WORKING_PLATFORM_TARGETS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def platform_working_target(platform: str) -> dict[str, Any]:
    p = str(platform or "").strip().lower()
    out = dict((load_working_platform_targets().get(p) or {}))
    if out:
        out.setdefault("platform", p)
    return out


def load_protected_platform_targets() -> dict[str, list[dict[str, Any]]]:
    try:
        if not _PROTECTED_PLATFORM_TARGETS.exists():
            return {}
        data = json.loads(_PROTECTED_PLATFORM_TARGETS.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_protected_platform_targets(data: dict[str, list[dict[str, Any]]]) -> None:
    try:
        _PROTECTED_PLATFORM_TARGETS.parent.mkdir(parents=True, exist_ok=True)
        _PROTECTED_PLATFORM_TARGETS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def target_identity(current: dict[str, Any]) -> dict[str, str]:
    if not isinstance(current, dict):
        return {}
    out = {
        "id": str(current.get("id") or "").strip(),
        "target_slug": str(current.get("target_slug") or current.get("slug") or "").strip(),
        "target_listing_id": str(current.get("target_listing_id") or current.get("listing_id") or "").strip(),
        "target_document_id": str(current.get("target_document_id") or current.get("document_id") or current.get("book_id") or "").strip(),
        "target_product_id": str(current.get("target_product_id") or current.get("product_id") or "").strip(),
        "url": str(current.get("url") or "").strip(),
    }
    return {k: v for k, v in out.items() if v}


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


def protect_platform_target(platform: str, current: dict[str, Any], *, reason: str = "manual_protect") -> None:
    p = str(platform or "").strip().lower()
    if not p or not isinstance(current, dict) or not current:
        return
    ref = target_identity(current)
    if not ref:
        return
    data = load_protected_platform_targets()
    items = list(data.get(p) or [])
    for item in items:
        if not isinstance(item, dict):
            continue
        old = target_identity(item)
        for key in ("id", "target_slug", "target_listing_id", "target_document_id", "target_product_id", "url"):
            if ref.get(key) and old.get(key) and ref.get(key) == old.get(key):
                item["protected_reason"] = str(item.get("protected_reason") or reason)
                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                data[p] = items
                save_protected_platform_targets(data)
                return
    fresh = dict(ref)
    fresh["platform"] = p
    fresh["protected_reason"] = str(reason or "manual_protect")
    fresh["updated_at"] = datetime.now(timezone.utc).isoformat()
    items.append(fresh)
    data[p] = items
    save_protected_platform_targets(data)


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
    if not target_id:
        return False
    if not bool(current.get("mutable", True)):
        return False
    if is_target_protected(str(current.get("platform") or current.get("_platform") or ""), current):
        return False
    if not current_task_root:
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
    elif p == "kofi" and rid:
        current["target_product_id"] = rid
    elif p == "printful" and rid:
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
    if current:
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        targets[p] = current
        save_working_platform_targets(targets)
