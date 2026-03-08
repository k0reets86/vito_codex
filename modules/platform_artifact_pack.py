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
import time

from config.paths import PROJECT_ROOT
from modules.image_utils import write_placeholder_png
from modules.listing_optimizer import optimize_listing_payload
from modules.pdf_utils import write_minimal_pdf
from modules.task_lineage import derive_artifact_map


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
        optional_fields=("materials", "who_made", "when_made", "is_supply", "short_description", "seo_title", "seo_description"),
        required_artifacts=("cover_path", "pdf_path"),
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
        optional_fields=("author", "subtitle", "categories", "short_description"),
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


def _safe_slug(text: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^\w\s-]", "", str(text or "").lower().strip())
    slug = re.sub(r"[\s_]+", "_", slug)
    slug = slug.strip("_")
    return slug[:max_len] or "vito_asset"


def generate_fresh_assets(
    topic: str,
    *,
    run_tag: str = "",
    output_dir: Path | None = None,
    task_root_id: str = "",
) -> dict[str, str]:
    """Generate a fresh local asset bundle for a single publish run.

    This deliberately avoids reusing older generic test assets from output/.
    """
    ts = run_tag.strip() or str(int(time.time()))
    slug = _safe_slug(topic, max_len=40)
    root = output_dir or (PROJECT_ROOT / "runtime" / "fresh_artifacts" / f"{slug}_{ts}")
    root.mkdir(parents=True, exist_ok=True)
    artifact_ids = derive_artifact_map(task_root_id) if str(task_root_id or "").strip() else {}
    file_prefix = str(task_root_id or "").strip() or slug

    cover_path = root / f"{file_prefix}_cover_1280x720.png"
    thumb_path = root / f"{file_prefix}_thumb_600x600.png"
    image_path = root / f"{file_prefix}_social_1200x630.png"
    preview1_path = root / f"{file_prefix}_preview_01_1280x720.png"
    preview2_path = root / f"{file_prefix}_preview_02_1280x720.png"
    pdf_path = root / f"{file_prefix}_product.pdf"
    write_minimal_pdf(
        "\n".join(
            [
                f"{topic[:80]} {ts}",
                topic[:120],
                "Fresh artifact bundle generated for platform upload",
                f"Run tag: {ts}",
                "Use this asset for workflow verification only.",
            ]
        ),
        str(pdf_path),
    )

    write_placeholder_png(str(cover_path), 1280, 720, text=(topic or "Digital Product")[:24])
    write_placeholder_png(str(thumb_path), 600, 600, text=(topic or "Digital Product")[:18])
    write_placeholder_png(str(image_path), 1200, 630, text=(topic or "Digital Product")[:22])
    write_placeholder_png(str(preview1_path), 1280, 720, text=f"{(topic or 'Digital Product')[:18]} Playbook")
    write_placeholder_png(str(preview2_path), 1280, 720, text=f"{(topic or 'Digital Product')[:18]} Checklist")

    return {
        "task_root_id": str(task_root_id or "").strip(),
        "pdf_path": str(pdf_path),
        "cover_path": str(cover_path),
        "thumb_path": str(thumb_path),
        "image_path": str(image_path),
        "preview_paths": [str(preview1_path), str(preview2_path)],
        "fresh_artifact_dir": str(root),
        "fresh_artifacts_only": True,
        "product_file_id": str(artifact_ids.get("product_file_id") or ""),
        "cover_id": str(artifact_ids.get("cover_id") or ""),
        "thumbnail_id": str(artifact_ids.get("thumbnail_id") or ""),
        "social_image_id": str(artifact_ids.get("social_image_id") or ""),
    }


def build_platform_bundle(platform: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build platform-ready payload with deterministic text + artifact defaults."""
    p = str(platform or "").strip().lower()
    base = dict(payload or {})
    title = str(base.get("title") or base.get("name") or "Working Product").strip()
    description = str(
        base.get("description")
        or base.get("text")
        or "Prepared listing asset pack with SEO-ready structure and media attached."
    ).strip()
    topic = str(base.get("topic") or "digital product automation").strip()
    slug = _slug(title or topic)
    fresh_only = bool(base.get("fresh_artifacts_only"))
    assets = (
        generate_fresh_assets(
            topic or title or "Working Product Asset",
            run_tag=str(base.get("run_tag") or "").strip(),
            task_root_id=str(base.get("task_root_id") or "").strip(),
        )
        if fresh_only
        else _default_assets()
    )

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
            "task_root_id": str(base.get("task_root_id") or assets.get("task_root_id") or ""),
        }
        out = optimize_listing_payload(p, seed)
        out.update({k: v for k, v in base.items() if v is not None})
        if fresh_only:
            out.setdefault("fresh_artifacts_only", True)
            out.setdefault("fresh_artifact_dir", assets.get("fresh_artifact_dir", ""))
        for key in ("product_file_id", "cover_id", "thumbnail_id", "social_image_id"):
            if assets.get(key):
                out.setdefault(key, assets.get(key, ""))
        if not out.get("preview_paths"):
            out["preview_paths"] = [x for x in assets.get("preview_paths", []) if str(x or "").strip()]
        if not out.get("preview_paths"):
            out["preview_paths"] = [x for x in [out.get("cover_path"), out.get("thumb_path")] if str(x or "").strip()]
        if p == "etsy":
            out.setdefault("materials", ["pdf", "digital download", "planner pages", "instant download"])
            out.setdefault("who_made", "i_did")
            out.setdefault("when_made", "made_to_order")
            out.setdefault("is_supply", False)
            out.setdefault("file_path", out.get("pdf_path") or "")
        if p == "amazon_kdp":
            author = str(base.get("author") or base.get("brand_name") or "Editorial Team").strip()
            subtitle = str(base.get("subtitle") or "Practical AI workflow kit for creators").strip()
            kw = list(out.get("keywords") or [])
            out.setdefault("author", author)
            out.setdefault("subtitle", subtitle)
            out.setdefault(
                "categories",
                base.get("categories") or ["Business & Money", "Computers & Technology"],
            )
            out.setdefault("file_path", out.get("pdf_path") or "")
            out.setdefault("manuscript_path", out.get("pdf_path") or "")
            out.setdefault("keyword_slots", kw[:7])
        return out

    if p == "twitter":
        text = str(base.get("text") or f"{title}. {topic}.").strip()
        return {
            "text": text[:280],
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            "task_root_id": str(base.get("task_root_id") or assets.get("task_root_id") or ""),
            "fresh_artifacts_only": fresh_only,
            "fresh_artifact_dir": assets.get("fresh_artifact_dir", ""),
            "social_image_id": str(assets.get("social_image_id") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    if p == "reddit":
        return {
            "subreddit": str(base.get("subreddit") or "test"),
            "title": str(base.get("title") or title)[:280],
            "text": str(base.get("text") or description)[:40000],
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            "task_root_id": str(base.get("task_root_id") or assets.get("task_root_id") or ""),
            "fresh_artifacts_only": fresh_only,
            "fresh_artifact_dir": assets.get("fresh_artifact_dir", ""),
            "social_image_id": str(assets.get("social_image_id") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    if p == "pinterest":
        return {
            "title": str(base.get("title") or title)[:100],
            "description": str(base.get("description") or description)[:500],
            "url": str(base.get("url") or f"https://example.com/{slug}"),
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            "task_root_id": str(base.get("task_root_id") or assets.get("task_root_id") or ""),
            "fresh_artifacts_only": fresh_only,
            "fresh_artifact_dir": assets.get("fresh_artifact_dir", ""),
            "social_image_id": str(assets.get("social_image_id") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    if p == "printful":
        sync_product = dict(base.get("sync_product") or {})
        if not sync_product.get("name"):
            sync_product["name"] = title[:120]
        sync_product.setdefault("thumbnail", str(base.get("image_path") or assets.get("image_path") or ""))
        return {
            "sync_product": sync_product,
            "sync_variants": base.get("sync_variants") or [],
            "image_path": str(base.get("image_path") or assets.get("image_path") or ""),
            "task_root_id": str(base.get("task_root_id") or assets.get("task_root_id") or ""),
            "fresh_artifacts_only": fresh_only,
            "fresh_artifact_dir": assets.get("fresh_artifact_dir", ""),
            "social_image_id": str(assets.get("social_image_id") or ""),
            **{k: v for k, v in base.items() if v is not None},
        }

    return dict(base)
