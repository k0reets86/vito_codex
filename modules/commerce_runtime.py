"""Runtime helpers for commerce execution agents."""

from __future__ import annotations

from typing import Any


def build_listing_runtime_profile(platform: str, status: str, verification: dict[str, Any] | None, contributors: list[str] | None) -> dict[str, Any]:
    ver = dict(verification or {})
    ok = bool(ver.get("ok", False))
    errors = [str(x).strip() for x in (ver.get("errors") or []) if str(x).strip()]
    return {
        "platform": str(platform or "").strip(),
        "status": str(status or "").strip(),
        "verification_ok": ok,
        "verification_errors": errors,
        "contributors": list(contributors or []),
        "next_actions": (
            ["repair_missing_artifacts", "rerun_verifier", "avoid_publish_success_claim"]
            if not ok
            else ["capture_public_proof", "handoff_to_social_pack", "record_platform_lesson"]
        ),
    }


def build_publisher_runtime_profile(platform: str, quality_score: Any, approved: bool) -> dict[str, Any]:
    score = int(quality_score or 0) if str(quality_score or "").strip() else 0
    ok = bool(approved)
    return {
        "platform": str(platform or "").strip(),
        "quality_score": score,
        "approved": ok,
        "next_actions": (
            ["revise_content", "rerun_quality_gate", "block_publish"]
            if not ok
            else ["capture_publish_url", "record_editorial_runbook", "handoff_to_distribution"]
        ),
    }

