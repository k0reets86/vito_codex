"""Unified platform result contract with evidence-first normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


ALLOWED_PLATFORM_STATUSES = {
    "ok",
    "success",
    "completed",
    "published",
    "created",
    "draft",
    "draft_saved",
    "prepared",
    "failed",
    "error",
    "not_configured",
    "not_authenticated",
    "needs_oauth",
    "needs_browser_flow",
    "daily_limit",
    "blocked",
    "dry_run",
}

SUCCESS_STATUSES = {"ok", "success", "completed", "published", "created"}


@dataclass
class PlatformContractValidation:
    ok: bool
    errors: list[str]


def normalize_platform_result(raw: Any, platform: str = "", action: str = "publish") -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    if raw is None:
        return {
            "status": "error",
            "platform": str(platform or "").strip().lower(),
            "action": str(action or "publish"),
            "error": "result_none",
            "message": "",
            "evidence": {},
            "data": {},
            "ts": now,
        }

    if isinstance(raw, str):
        txt = str(raw).strip()
        return {
            "status": "success" if txt else "error",
            "platform": str(platform or "").strip().lower(),
            "action": str(action or "publish"),
            "error": "" if txt else "result_empty_text",
            "message": txt,
            "evidence": {},
            "data": {"text": txt},
            "ts": now,
        }

    if not isinstance(raw, dict):
        return {
            "status": "error",
            "platform": str(platform or "").strip().lower(),
            "action": str(action or "publish"),
            "error": "result_not_dict",
            "message": "",
            "evidence": {},
            "data": {"value": str(raw)},
            "ts": now,
        }

    status = str(raw.get("status", "")).strip().lower() or "ok"
    platform_val = str(raw.get("platform") or platform or "").strip().lower()
    evidence = {
        "url": str(raw.get("url") or raw.get("public_url") or raw.get("product_url") or raw.get("post_url") or raw.get("tweet_url") or "").strip(),
        "id": str(raw.get("id") or raw.get("post_id") or raw.get("tweet_id") or raw.get("listing_id") or raw.get("product_id") or "").strip(),
        "path": str(raw.get("file_path") or raw.get("path") or "").strip(),
        "screenshot": str(raw.get("screenshot_path") or "").strip(),
    }
    return {
        "status": status,
        "platform": platform_val,
        "action": str(action or "publish"),
        "error": str(raw.get("error") or "").strip(),
        "message": str(raw.get("message") or raw.get("detail") or "").strip(),
        "evidence": evidence,
        "data": dict(raw),
        "ts": now,
    }


def validate_platform_result_contract(payload: dict[str, Any], require_evidence_for_success: bool = True) -> PlatformContractValidation:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return PlatformContractValidation(False, ["payload_not_dict"])
    status = str(payload.get("status", "")).strip().lower()
    if not status:
        errors.append("status_missing")
    elif status not in ALLOWED_PLATFORM_STATUSES:
        errors.append("status_invalid")

    evidence = payload.get("evidence")
    if evidence is None:
        evidence = {}
    if not isinstance(evidence, dict):
        errors.append("evidence_not_dict")
        evidence = {}
    if require_evidence_for_success and status in SUCCESS_STATUSES:
        has_evidence = any(str(evidence.get(k) or "").strip() for k in ("url", "id", "path", "screenshot"))
        if not has_evidence:
            errors.append("success_without_evidence")
    return PlatformContractValidation(len(errors) == 0, errors)

