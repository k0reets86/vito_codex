"""Strict step result contract for DecisionLoop agent/tool outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StepContractResult:
    ok: bool
    errors: list[str]


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
        # Status (if present) must be known-like
        status = str(output.get("status", "")).strip().lower()
        if status and status not in {
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
        }:
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
