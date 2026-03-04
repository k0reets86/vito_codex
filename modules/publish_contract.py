"""Publish contract helpers for platform pipelines.

Enforces:
- Required product card fields
- Deduplication by signature
- Explicit policy flags for risky operations
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from modules.listing_optimizer import get_platform_spec

DB_PATH = Path("/home/vito/vito-agent/memory/vito_local.db")


def normalize_publish_payload(platform: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return normalized payload for validation/signature."""
    return {
        "platform": platform,
        "name": str(payload.get("name", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
        "price": int(payload.get("price", 0) or 0),
        "pdf_path": str(payload.get("pdf_path", "")).strip(),
        "cover_path": str(payload.get("cover_path", "")).strip(),
        "thumb_path": str(payload.get("thumb_path", "")).strip(),
        "category": str(payload.get("category", "")).strip(),
        "tags": [str(x).strip().lower() for x in (payload.get("tags") or []) if str(x).strip()],
        "draft_only": bool(payload.get("draft_only", False)),
    }


def validate_publish_payload(platform: str, payload: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate mandatory product card fields."""
    p = normalize_publish_payload(platform, payload)
    spec = get_platform_spec(platform)
    errors: list[str] = []

    if not p["name"] or len(p["name"]) < int(spec.get("title_min", 6)):
        errors.append("invalid_name")
    if len(p["name"]) > int(spec.get("title_max", 120)):
        errors.append("name_too_long")
    if not p["description"] or len(p["description"]) < 40:
        errors.append("invalid_description")
    if p["price"] < 1:
        errors.append("invalid_price")
    if not p["pdf_path"] or not Path(p["pdf_path"]).exists():
        errors.append("missing_pdf")
    if not p["cover_path"] or not Path(p["cover_path"]).exists():
        errors.append("missing_cover")
    if not p["thumb_path"] or not Path(p["thumb_path"]).exists():
        errors.append("missing_thumb")

    # For real publish (not draft), require category/tags.
    if not p["draft_only"]:
        if not p["category"]:
            errors.append("missing_category")
        if len(p["tags"]) < 2:
            errors.append("missing_tags")
    if len(p["tags"]) > int(spec.get("tags_max", 16)):
        errors.append("too_many_tags")
    if any(len(t) > int(spec.get("tag_max_len", 64)) for t in p["tags"]):
        errors.append("tag_too_long")

    return (len(errors) == 0, errors, p)


def build_publish_signature(platform: str, payload: dict[str, Any]) -> str:
    p = normalize_publish_payload(platform, payload)
    stable = {
        "platform": p["platform"],
        "name": p["name"].lower(),
        "price": p["price"],
        "pdf_path": p["pdf_path"],
        "cover_path": p["cover_path"],
        "thumb_path": p["thumb_path"],
        "category": p["category"].lower(),
        "tags": sorted(p["tags"]),
        "draft_only": p["draft_only"],
    }
    raw = json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def recent_duplicate_publish(signature: str, hours: int = 24) -> bool:
    """Check duplicate publish attempts by signature."""
    if not DB_PATH.exists():
        return False
    q = """
        SELECT 1
        FROM execution_facts
        WHERE action IN ('platform:publish_attempt', 'platform:publish')
          AND detail LIKE ?
          AND datetime(created_at) >= datetime('now', ?)
        LIMIT 1
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(q, (f"%sig={signature}%", f"-{int(hours)} hours")).fetchone()
        return row is not None
