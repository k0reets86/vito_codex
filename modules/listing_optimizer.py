"""Deterministic listing optimizer for marketplace publication payloads.

Goal:
- fill missing listing fields with safe defaults
- enforce platform-aware limits for title/tags/meta
- build SEO helper fields without extra LLM calls
"""

from __future__ import annotations

import re
from typing import Any


_WORD_RE = re.compile(r"[a-zA-Zа-яА-Я0-9][a-zA-Zа-яА-Я0-9\-\+_]{1,}")

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "как", "что", "или",
    "для", "это", "она", "они", "его", "её", "без", "под", "над", "через", "while", "when", "where",
}

_SPECS: dict[str, dict[str, int]] = {
    "gumroad": {
        "title_min": 8,
        "title_max": 100,
        "tags_max": 5,
        "tag_max_len": 32,
        "desc_min": 120,
        "short_max": 180,
    },
    "etsy": {
        "title_min": 8,
        "title_max": 140,
        "tags_max": 13,
        "tag_max_len": 20,
        "desc_min": 180,
        "short_max": 220,
    },
    "kofi": {
        "title_min": 6,
        "title_max": 120,
        "tags_max": 10,
        "tag_max_len": 32,
        "desc_min": 120,
        "short_max": 180,
    },
    "amazon_kdp": {
        "title_min": 8,
        "title_max": 200,
        "tags_max": 7,
        "tag_max_len": 50,
        "desc_min": 200,
        "short_max": 220,
    },
}


def get_platform_spec(platform: str) -> dict[str, int]:
    p = str(platform or "").strip().lower()
    return _SPECS.get(p, _SPECS["gumroad"]).copy()


def _clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clip(text: str, max_len: int) -> str:
    t = _clean_spaces(text)
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _extract_keywords(*parts: str, limit: int = 24) -> list[str]:
    raw = " ".join(_clean_spaces(p).lower() for p in parts if p)
    out: list[str] = []
    seen = set()
    for m in _WORD_RE.findall(raw):
        token = m.strip("-_+")
        if len(token) < 3:
            continue
        if token in _STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= limit:
            break
    return out


def _dedup_tags(tags: list[str], max_count: int, max_len: int) -> list[str]:
    out: list[str] = []
    seen = set()
    for t in tags:
        x = _clean_spaces(str(t or "").lower())
        if not x:
            continue
        x = re.sub(r"[^\w\s\-\+]", "", x).strip()
        x = _clip(x, max_len)
        if len(x) < 2:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
        if len(out) >= max_count:
            break
    return out


def _fallback_description(title: str, keywords: list[str]) -> str:
    base = (
        f"{title}. Practical digital product focused on clear outcomes, fast onboarding, "
        "and repeatable execution workflow."
    )
    if keywords:
        base += " Includes: " + ", ".join(keywords[:8]) + "."
    base += " Suitable for creators, solo founders, and automation-first teams."
    return base


def _infer_category(platform: str, title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    if any(x in text for x in ("prompt", "ai", "automation", "agent", "бот", "нейро")):
        return "Programming" if platform == "gumroad" else "Digital"
    if any(x in text for x in ("template", "notion", "planner", "checklist", "pdf")):
        return "Productivity" if platform == "gumroad" else "Templates"
    if any(x in text for x in ("курс", "guide", "ebook", "book", "learn", "обуч")):
        return "Education"
    return "Digital"


def _build_score(payload: dict[str, Any], spec: dict[str, int]) -> int:
    score = 0
    title = str(payload.get("name") or payload.get("title") or "")
    desc = str(payload.get("description") or "")
    tags = payload.get("tags") or []
    category = str(payload.get("category") or "")
    has_main_file = bool(payload.get("pdf_path") or payload.get("file_path"))
    has_cover = bool(payload.get("cover_path"))
    has_thumb = bool(payload.get("thumb_path"))
    if spec["title_min"] <= len(title) <= spec["title_max"]:
        score += 20
    if len(desc) >= spec["desc_min"]:
        score += 20
    if len(tags) >= min(3, spec["tags_max"]):
        score += 20
    if category:
        score += 20
    if has_main_file and (has_cover or has_thumb):
        score += 20
    return score


def optimize_listing_payload(platform: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return payload enriched with platform-aware SEO fields and defaults."""
    p = str(platform or "").strip().lower()
    spec = get_platform_spec(p)
    data = dict(payload or {})

    raw_title = (
        str(data.get("name") or data.get("title") or data.get("product_name") or "").strip()
        or "VITO Digital Product"
    )
    title = _clip(raw_title, spec["title_max"])
    if len(title) < spec["title_min"]:
        title = _clip(f"{title} Toolkit", spec["title_max"])

    raw_description = str(
        data.get("description")
        or data.get("long_description")
        or data.get("content")
        or ""
    ).strip()
    base_keywords = _extract_keywords(title, raw_description, str(data.get("topic") or ""))
    description = _clean_spaces(raw_description)
    if len(description) < spec["desc_min"]:
        description = _fallback_description(title, base_keywords)
    if len(description) < spec["desc_min"]:
        description = (description + " " + _fallback_description(title, base_keywords)).strip()

    source_tags = data.get("tags") or []
    if not isinstance(source_tags, list):
        source_tags = [str(source_tags)]
    if not source_tags:
        source_tags = base_keywords[: spec["tags_max"]]
    tags = _dedup_tags(source_tags, spec["tags_max"], spec["tag_max_len"])
    if len(tags) < min(3, spec["tags_max"]):
        tags = _dedup_tags(tags + base_keywords, spec["tags_max"], spec["tag_max_len"])

    category = str(data.get("category") or "").strip()
    if not category:
        category = _infer_category(p, title, description)

    short_description = str(data.get("short_description") or data.get("summary") or "").strip()
    if not short_description:
        short_description = description.split(".")[0].strip()
    short_description = _clip(short_description, spec["short_max"])

    seo_title = _clip(str(data.get("seo_title") or title), 60)
    seo_description = _clip(str(data.get("seo_description") or short_description or description), 160)

    preview_paths = []
    for key in ("preview_paths", "images", "listing_images", "files"):
        val = data.get(key)
        if isinstance(val, list):
            preview_paths.extend([str(x) for x in val if str(x).strip()])
    for key in ("cover_path", "thumb_path", "preview_path"):
        val = str(data.get(key) or "").strip()
        if val:
            preview_paths.append(val)
    # Dedup preserve order
    seen = set()
    preview_paths_dedup = []
    for pth in preview_paths:
        if pth in seen:
            continue
        seen.add(pth)
        preview_paths_dedup.append(pth)

    out = dict(data)
    out["name"] = title
    out["title"] = title
    out["description"] = description
    out["long_description"] = description
    out["summary"] = short_description
    out["short_description"] = short_description
    out["category"] = category
    out["tags"] = tags
    out["seo_title"] = seo_title
    out["seo_description"] = seo_description
    out["keywords"] = _dedup_tags(base_keywords, 20, 32)
    out["preview_paths"] = preview_paths_dedup
    out["seo_score"] = _build_score(out, spec)
    out["publish_ready"] = bool(out["seo_score"] >= 80)
    return out

