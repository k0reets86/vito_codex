"""Owner-grade validation helpers for platform execution results."""

from __future__ import annotations

from typing import Any


def validate_owner_grade_repeatability(result: dict[str, Any]) -> tuple[bool, list[str]]:
    if not isinstance(result, dict):
        return False, ["result_not_dict"]
    profile = result.get("repeatability_profile")
    if not isinstance(profile, dict):
        return False, ["missing_repeatability_profile"]
    errors: list[str] = []
    if not bool(profile.get("owner_grade_ready")):
        errors.append("owner_grade_not_ready")
    if int(profile.get("proof_count") or 0) < 2:
        errors.append("insufficient_proof_channels")
    missing_required = list(profile.get("missing_required_artifacts") or [])
    if missing_required:
        errors.append(f"missing_required:{','.join(sorted(str(x) for x in missing_required))}")
    status = str(profile.get("status") or "").strip().lower()
    if status not in {"draft", "created", "published", "success", "completed", "ok", "prepared"}:
        errors.append("invalid_status_for_owner_grade")
    return len(errors) == 0, errors

