"""Repeatability/evidence helpers for platform adapters."""

from __future__ import annotations

from typing import Any


def build_publish_repeatability_profile(
    *,
    platform: str,
    status: str,
    mode: str,
    has_url: bool,
    has_id: bool,
    has_screenshot: bool,
    artifact_flags: dict[str, Any] | None = None,
    required_artifacts: list[str] | tuple[str, ...] | None = None,
    recovery_hints: list[str] | None = None,
) -> dict[str, Any]:
    flags = {
        str(k): bool(v)
        for k, v in dict(artifact_flags or {}).items()
        if str(k).strip()
    }
    required = [str(name).strip() for name in (required_artifacts or flags.keys()) if str(name).strip()]
    confirmed_artifacts = [name for name, ok in flags.items() if ok]
    blocked_artifacts = [name for name, ok in flags.items() if not ok]
    missing_required = [name for name in required if not flags.get(name)]
    verification_channels: list[str] = []
    if has_id:
        verification_channels.append("id")
    if has_url:
        verification_channels.append("url")
    if has_screenshot:
        verification_channels.append("screenshot")
    proof_count = len(verification_channels)
    owner_grade_ready = proof_count >= 2 and not missing_required and str(status or "").strip().lower() in {
        "draft",
        "created",
        "published",
        "success",
        "completed",
        "ok",
        "prepared",
    }
    return {
        "platform": str(platform or "").strip(),
        "status": str(status or "").strip() or "unknown",
        "mode": str(mode or "").strip() or "unknown",
        "has_url": bool(has_url),
        "has_id": bool(has_id),
        "has_screenshot": bool(has_screenshot),
        "confirmed_artifacts": confirmed_artifacts,
        "missing_artifacts": blocked_artifacts,
        "required_artifacts": required,
        "missing_required_artifacts": missing_required,
        "verification_channels": verification_channels,
        "proof_count": proof_count,
        "owner_grade_ready": owner_grade_ready,
        "repeatability_grade": (
            "owner_grade"
            if owner_grade_ready
            else ("strong" if (has_url or has_id) and not missing_required else "partial")
        ),
        "recovery_hints": list(recovery_hints or []),
    }


def attach_publish_repeatability(
    result: dict[str, Any],
    *,
    platform: str,
    mode: str,
    id_keys: tuple[str, ...] = ("id", "listing_id", "post_id", "tweet_id", "story_id", "product_id"),
    url_keys: tuple[str, ...] = ("url", "permalink", "post_url", "edit_url"),
    screenshot_keys: tuple[str, ...] = ("screenshot_path", "editor_audit", "screenshot"),
    artifact_flags: dict[str, Any] | None = None,
    required_artifacts: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    out = dict(result or {})
    status = str(out.get("status") or "").strip() or "unknown"
    has_id = any(str(out.get(k) or "").strip() for k in id_keys)
    has_url = any(str(out.get(k) or "").strip() for k in url_keys)
    has_screenshot = any(
        (str(out.get(k) or "").strip() if not isinstance(out.get(k), dict) else bool(out.get(k)))
        for k in screenshot_keys
    )
    hints = list(out.get("recovery_hints") or [])
    out["repeatability_profile"] = build_publish_repeatability_profile(
        platform=platform,
        status=status,
        mode=mode,
        has_url=has_url,
        has_id=has_id,
        has_screenshot=has_screenshot,
        artifact_flags=artifact_flags,
        required_artifacts=required_artifacts,
        recovery_hints=hints,
    )
    return out


def build_analytics_repeatability_profile(
    *,
    platform: str,
    ok: bool,
    has_raw_data: bool,
    source: str,
) -> dict[str, Any]:
    return {
        "platform": str(platform or "").strip(),
        "status": "ok" if ok else "failed",
        "source": str(source or "").strip() or "unknown",
        "has_raw_data": bool(has_raw_data),
        "repeatability_grade": "strong" if ok and has_raw_data else ("partial" if ok else "failed"),
    }


def attach_analytics_repeatability(
    result: dict[str, Any],
    *,
    platform: str,
    source: str,
) -> dict[str, Any]:
    out = dict(result or {})
    status = str(out.get("status") or "").strip().lower()
    ok = status in {"ok", "published", "draft", "prepared"}
    has_raw = bool(out.get("raw_data") or out.get("output") or out.get("analytics"))
    out["repeatability_profile"] = build_analytics_repeatability_profile(
        platform=platform,
        ok=ok,
        has_raw_data=has_raw,
        source=source,
    )
    return out
