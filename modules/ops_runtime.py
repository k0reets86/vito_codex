"""Runtime profiles for operational governance agents."""

from __future__ import annotations

from typing import Any


def build_devops_runtime_profile(
    *,
    operation: str,
    success: bool,
    issue_count: int = 0,
    can_auto_remediate: bool = False,
) -> dict[str, Any]:
    return {
        "operation": str(operation or "").strip() or "unknown",
        "success": bool(success),
        "issue_count": max(int(issue_count or 0), 0),
        "can_auto_remediate": bool(can_auto_remediate),
        "next_actions": (
            ["log_ops_evidence", "monitor_post_fix_state", "attach_runtime_snapshot"]
            if success
            else ["route_to_self_healer", "collect_logs", "request_targeted_retry"]
        ),
    }


def build_security_runtime_profile(
    *,
    operation: str,
    risk_score: float | int,
    missing_count: int = 0,
    weak_count: int = 0,
    block_recommended: bool = False,
) -> dict[str, Any]:
    return {
        "operation": str(operation or "").strip() or "unknown",
        "risk_score": float(risk_score or 0.0),
        "missing_count": max(int(missing_count or 0), 0),
        "weak_count": max(int(weak_count or 0), 0),
        "block_recommended": bool(block_recommended),
        "next_actions": (
            ["open_security_block", "request_secret_rotation", "rerun_security_scan"]
            if block_recommended
            else ["log_security_posture", "continue_with_monitoring"]
        ),
    }
