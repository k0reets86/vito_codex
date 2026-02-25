"""Response contract validation for tooling runtime outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolingContractResult:
    ok: bool
    errors: list[str]


def validate_tooling_response(output: Any) -> ToolingContractResult:
    errs: list[str] = []
    if not isinstance(output, dict):
        return ToolingContractResult(False, ["output_not_dict"])
    status = str(output.get("status", "")).strip().lower()
    if status not in {"ok", "success", "prepared", "dry_run", "failed", "error"}:
        errs.append("status_invalid")
    if not str(output.get("adapter_key", "")).strip():
        errs.append("adapter_key_missing")
    if not str(output.get("protocol", "")).strip():
        errs.append("protocol_missing")
    if status in {"failed", "error"} and not str(output.get("error", "")).strip():
        errs.append("error_missing")
    return ToolingContractResult(len(errs) == 0, errs)
