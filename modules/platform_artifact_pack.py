"""Platform artifact packs: deterministic preflight bundle for publication.

Purpose:
- define what must be prepared before publish per platform
- build complete payloads (texts + media/file artifacts) up-front
- reduce random "fill-on-the-fly" behavior in adapters
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

from config.paths import PROJECT_ROOT
from modules.listing_optimizer import optimize_listing_payload


@dataclass(frozen=True)
class PlatformPack:
    platform: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    required_artifacts: tuple[str, ...]
    notes: str = ""


PLATFORM_PACKS: dict[str, PlatformPack] = {
    "gumroad": PlatformPack(
        platform="gumroad",
        required_fields=("name", "description", "price", "category", "tags"),
        optional_fields=("summary",),
        required_artifacts=("pdf_path", "cover_path", "thumb_path"),
        notes="Digital product listing with file delivery and SEO card fields.",
    ),
    "etsy": PlatformPack(
        platform="etsy",
        required_fields=("title", "description", "price", "category", "tags"),
        optional_fields=("materials", "who_made", "when_made", "is_supply"),
        required_artifacts=("cover_path",),
        notes="Listing editor requires visual + mandatory taxonomy/profile fields in UI.",
    ),
    "kofi": PlatformPack(
        platform="kofi",
        required_fields=("title", "description", "price"),
        optional_fields=("category", "tags"),
        required_artifacts=("cover_path",),
        notes="Shop/settings path + payment provider setup gates product publishing.",
    ),
    "amazon_kdp": PlatformPack(
        platform="amazon_kdp",
        required_fields=("title", "description", "keywords"),
        optional_fields=("author", "subtitle"),
        required_artifacts=("pdf_path", "cover_path"),
        notes="Draft requires manuscript/cover pipeline and bookshelf confirmation.",
    ),
    "twitter": PlatformPack(
        platform="twitter",
        required_fields=("text",),
        optional_fields=("hashtags",),
        required_artifacts=("image_path",),
        notes="Single post with optional media and permalink evidence.",
    ),
    "reddit": PlatformPack(
        platform="reddit",
        required_fields=("subreddit", "title"),
        optional_fields=("text", "url"),
        required_artifacts=("image_path",),
        notes="Prefer modern submit flow; permalink verification required.",
    ),
    "pinterest": PlatformPack(
        platform="pinterest",
        required_fields=("title", "description", "url"),
        optional_fields=("board",),
        required_artifacts=("image_path",),
        notes="Pin creation tool requires board selection + anti-bot tolerant session.",
    ),
    "printful": PlatformPack(
        platform="printful",
        required_fields=("sync_product", "sync_variants"),
        optional_fields=("store_id",),
        required_artifacts=("image_path",),
        notes="Etsy-connected stores typically require browser flow, not /store/products API.",
    ),
}


def get_platform_pack(platform: str) -> PlatformPack | None:
    return PLATFORM_PACKS.get(str(platform or "").strip().lower())


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    if not s:
        s = "vito-item"
    return s[:max_len].strip("-") or "vito-item"


def _pick_existing(paths: list[Path]) -> str:
    for p in paths:
        if p.exists() and p.is_file():
            return str(p)
    return ""


def _default_assets() -> dict[str, str]:
    out = PROJECT_ROOT / "output"
    return {
        "pdf_path": _pick_existing([
            out / "The_AI_Side_Hustle_Playbook_v2.pdf",
            out / "products" / "vito_test_product.pdf",
            out / "ebooks" / "vito_test_ebook.pdf",
        ]),
        "cover_path": _pick_existing([
            out / "ai_side_hustle_cover_1280x720.png",
            out / "ai_side_hustle_cover_no_price.png",
            out / "images" / "cover_default.png",
        ]),
        "thumb_path": _pick_existing([
            out / "ai_side_hustle_thumb_600x600.png",
            out / "images" / "thumb_default.png",
        ]),
        "image_path": _pick_existing([
            out / "social" / "vito_social_test.png",
            out / "ai_side_hustle_thumb_600x600.png",
            out / "ai_side_hustle_cover_1280x720.png",
        ]),
    }


def build_platform_bundle(platform: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build platform-ready payload with deterministic text + artifact defaults."""
    p = str(platform or "").strip().lower()
    base = dict(payload or {})
    assets = _default_assets()
    title = str(base.get("title") or base.get("name") or "VITO Test Asset").strip()
    description = str(
        base.get("description")
        or base.get("text")
        or "Automated listing created by VITO preflight artifact pack. SEO-ready structure and media attached."
    ).strip()
    topic = str(base.get("topic") or "digital product automation").strip()
    slug = _slug(title or topic)

    if p in {"gumroad", "etsy", "kofi", "amazon_kdp"}:
        seed = {
            "name": title,
            "title": title,
            "description": description,
            "price": int(base.get("price", 5) or 5),
            "category": str(base.get("category") or "Digital"),
            "tags": base.get("tags") or ["vito", "automation", "digital", "ai", "workflow"],
            "cover_path": str(base.get("cover_path") or assets.get("cover_path") or ""),
            "thumb_path": str(base.get("thumb_path") or assets.get("thumb_path") or ""),
            "pdf_path": str(base.get("pdf_path") or assets.get("pdf_path") or ""),
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            "slug": str(base.get("slug") or slug),
            "topic": topic,
        }
        out = optimize_listing_payload(p, seed)
        out.update({k: v for k, v in base.items() if v is not None})
        return out

    if p == "twitter":
        text = str(base.get("text") or f"{title} — automation test by VITO. {topic}.").strip()
        return {
            "text": text[:280],
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    if p == "reddit":
        return {
            "subreddit": str(base.get("subreddit") or "test"),
            "title": str(base.get("title") or title)[:280],
            "text": str(base.get("text") or description)[:40000],
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    if p == "pinterest":
        return {
            "title": str(base.get("title") or title)[:100],
            "description": str(base.get("description") or description)[:500],
            "url": str(base.get("url") or f"https://example.com/{slug}"),
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    if p == "printful":
        return {
            "sync_product": base.get("sync_product") or {"name": title[:120]},
            "sync_variants": base.get("sync_variants") or [],
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    return dict(base)

