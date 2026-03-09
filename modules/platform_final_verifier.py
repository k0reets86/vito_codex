"""Unified final verification for platform publish/listing results.

This module is the single source of truth for fail-closed platform success.
It does not decide recipe-specific acceptance, but it does decide whether a
platform result is structurally and qualitatively strong enough to be treated
as a valid completed execution candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.platform_publish_quality import validate_platform_publish_quality
from modules.platform_result_contract import normalize_platform_result, validate_platform_result_contract


@dataclass
class PlatformFinalVerification:
    ok: bool
    normalized: dict[str, Any]
    errors: list[str]


def verify_platform_result(
    platform: str,
    result: dict[str, Any] | Any,
    payload: dict[str, Any] | None = None,
    *,
    action: str = "publish",
    require_evidence_for_success: bool = True,
) -> PlatformFinalVerification:
    normalized = normalize_platform_result(result or {}, platform=platform, action=action)
    errors: list[str] = []

    contract = validate_platform_result_contract(
        normalized,
        require_evidence_for_success=require_evidence_for_success,
    )
    if not contract.ok:
        errors.extend([f"platform_contract_invalid:{err}" for err in contract.errors])

    quality_ok, quality_errors = validate_platform_publish_quality(platform, result or {}, payload or {})
    if not quality_ok:
        errors.extend([f"publish_quality_gate_failed:{err}" for err in quality_errors])

    return PlatformFinalVerification(ok=not errors, normalized=normalized, errors=errors)
