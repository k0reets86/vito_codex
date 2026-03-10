"""Helpers for building structured capability pack runtime results."""

from __future__ import annotations

from typing import Any


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def missing_fields(input_data: dict[str, Any], required: list[str]) -> list[str]:
    return [field for field in required if not _nonempty(input_data.get(field))]


def error_result(code: str, *, capability: str, missing: list[str] | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "error": code,
        "output": {
            "capability": capability,
            "verification_ok": False,
            "missing_fields": list(missing or []),
            "next_actions": [f"provide:{field}" for field in (missing or [])],
            "recovery_hints": ["retry_with_complete_payload", "keep_task_root_binding"],
            "details": dict(details or {}),
        },
    }


def success_result(
    capability: str,
    *,
    output: dict[str, Any],
    evidence: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
    recovery_hints: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload = dict(output or {})
    payload.setdefault("capability", capability)
    payload.setdefault("verification_ok", True)
    payload.setdefault("evidence", dict(evidence or {}))
    payload.setdefault("next_actions", list(next_actions or []))
    payload.setdefault("recovery_hints", list(recovery_hints or []))
    if warnings:
        payload["warnings"] = list(warnings)
    return {"status": "ok", "output": payload}
