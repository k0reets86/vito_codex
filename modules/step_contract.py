"""Strict step result contract for DecisionLoop agent/tool outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.platform_result_contract import normalize_platform_result, validate_platform_result_contract

@dataclass
class StepContractResult:
    ok: bool
    errors: list[str]


ALLOWED_OUTPUT_STATUSES = {
    "ok",
    "success",
    "completed",
    "published",
    "created",
    "failed",
    "error",
    "not_configured",
    "not_authenticated",
    "needs_oauth",
    "daily_limit",
    "dry_run",
    "prepared",
    "blocked",
}


def validate_step_output(output: Any, metadata: dict | None = None) -> StepContractResult:
    errors: list[str] = []
    md = metadata or {}

    if output is None:
        errors.append("output_none")
        return StepContractResult(False, errors)

    if isinstance(output, str):
        if not output.strip():
            errors.append("output_empty_text")
        return StepContractResult(len(errors) == 0, errors)

    if isinstance(output, dict):
        # Unified platform result contract: normalize + validate whenever platform-ish payload is detected.
        if any(k in output for k in ("platform", "product_id", "post_id", "listing_id", "tweet_id", "publish")):
            normalized = normalize_platform_result(output, platform=str(output.get("platform", "") or ""))
            pv = validate_platform_result_contract(normalized, require_evidence_for_success=True)
            if not pv.ok:
                errors.extend([f"platform_contract:{e}" for e in pv.errors])
        # Status (if present) must be known-like
        status = str(output.get("status", "")).strip().lower()
        if status and status not in ALLOWED_OUTPUT_STATUSES:
            errors.append("status_unknown")

        # For publish-like outputs require at least one evidence field.
        if any(k in output for k in ("platform", "publish", "published", "product_id", "url")):
            has_evidence = any(
                bool(output.get(k))
                for k in ("url", "screenshot_path", "product_id", "post_id", "listing_id", "tweet_id")
            )
            if not has_evidence and status in {"completed", "published", "created", "success"}:
                errors.append("publish_without_evidence")

        # If metadata has file path, it must not be empty
        if "file_path" in md and not str(md.get("file_path", "")).strip():
            errors.append("metadata_file_path_empty")
        return StepContractResult(len(errors) == 0, errors)

    # allow list-like outputs for some agents but must be non-empty
    if isinstance(output, (list, tuple)):
        if len(output) == 0:
            errors.append("output_empty_list")
        return StepContractResult(len(errors) == 0, errors)

    # unknown type
    errors.append("output_unsupported_type")
    return StepContractResult(False, errors)


def validate_step_result(result: Any) -> StepContractResult:
    """Validate DecisionLoop step envelope: status + output/error shape."""
    errors: list[str] = []
    if not isinstance(result, dict):
        return StepContractResult(False, ["result_not_dict"])

    status = str(result.get("status", "")).strip().lower()
    if status not in {"completed", "failed", "waiting_approval"}:
        errors.append("result_status_invalid")
        return StepContractResult(False, errors)

    if status == "completed":
        if "output" not in result:
            errors.append("result_output_missing")
        else:
            metadata = {}
            if "file_path" in result:
                metadata["file_path"] = result.get("file_path")
            out_contract = validate_step_output(result.get("output"), metadata)
            if not out_contract.ok:
                errors.extend([f"output:{e}" for e in out_contract.errors])

    if status in {"failed", "waiting_approval"}:
        if not str(result.get("error", "")).strip():
            errors.append("result_error_missing")

    if "file_path" in result and not isinstance(result.get("file_path"), str):
        errors.append("result_file_path_invalid")

    return StepContractResult(len(errors) == 0, errors)
