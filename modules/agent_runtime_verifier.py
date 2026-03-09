"""Runtime verifier for agent contracts and collaboration behavior.

Phase F goal: make agent contracts operational at dispatch-time, not just descriptive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentRuntimeVerification:
    ok: bool
    errors: list[str]


def _lookup(obj: Any, path: str) -> Any:
    cur = obj
    for part in str(path or "").split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur.get(part)
        else:
            return None
    return cur


_COMMON_ALIASES: dict[str, list[str]] = {
    "status": ["status", "metadata.status"],
    "account": ["account", "platform", "email", "metadata.account"],
    "auth_state": ["auth_state", "verified", "metadata.auth_state"],
    "approved": ["approved", "metadata.approved"],
    "score": ["score", "metadata.score", "quality_score"],
    "feedback": ["feedback", "reason", "notes", "metadata.feedback"],
}


_AGENT_ALIASES: dict[str, dict[str, list[str]]] = {
    "browser_agent": {
        "page_url": ["url", "page_url", "metadata.page_url"],
        "dom_signal": ["verified", "verify", "dom_signal", "metadata.dom_signal", "title", "text"],
        "screenshot_or_trace": ["screenshot_path", "trace_path", "metadata.screenshot_path"],
    },
    "ecommerce_agent": {
        "platform_status": ["status", "platform_status", "metadata.platform_status"],
        "listing_id_or_url": ["url", "listing_id", "id", "metadata.listing_id", "metadata.url"],
        "artifact_manifest": [
            "artifact_manifest",
            "metadata.artifact_manifest",
            "payload.artifact_manifest",
            "_artifact_manifest",
        ],
    },
    "account_manager": {
        "account": ["account", "platform", "metadata.account"],
        "auth_state": ["auth_state", "configured", "verified", "status", "metadata.auth_state"],
    },
    "quality_judge": {
        "score": ["score", "quality_score", "metadata.score"],
        "approved": ["approved", "metadata.approved"],
        "feedback": ["feedback", "reason", "summary", "metadata.feedback"],
    },
}


def _truthy_evidence(agent_name: str, evidence_key: str, output: Any, metadata: dict[str, Any] | None) -> bool:
    aliases = list(_COMMON_ALIASES.get(evidence_key, []))
    aliases.extend(_AGENT_ALIASES.get(agent_name, {}).get(evidence_key, []))
    payload = output if isinstance(output, dict) else {}
    md = metadata if isinstance(metadata, dict) else {}
    for path in aliases or [evidence_key]:
        value = _lookup({"metadata": md, **payload}, path)
        if isinstance(value, bool):
            if value:
                return True
        elif isinstance(value, (int, float)):
            if value > 0:
                return True
        elif isinstance(value, (list, dict)):
            if value:
                return True
        elif str(value or "").strip():
            return True
    return False


def validate_agent_runtime_contract(
    *,
    agent_name: str,
    task_type: str,
    output: Any,
    metadata: dict[str, Any] | None,
    contract: dict[str, Any] | None,
    orchestration_plan: dict[str, Any] | None = None,
) -> AgentRuntimeVerification:
    errors: list[str] = []
    contract = dict(contract or {})
    metadata = dict(metadata or {})
    enforced = bool(contract.get("runtime_enforced", False))
    if not enforced:
        return AgentRuntimeVerification(ok=True, errors=[])

    if not isinstance(output, dict):
        return AgentRuntimeVerification(ok=False, errors=["runtime_contract_requires_dict_output"])

    for key in list(contract.get("required_evidence") or []):
        if not _truthy_evidence(agent_name, str(key), output, metadata):
            errors.append(f"missing_required_evidence:{key}")

    collab = metadata.get("collaboration_contract")
    if contract.get("collaborates_with") and not isinstance(collab, dict):
        errors.append("missing_collaboration_contract")

    verify_cap = ""
    if isinstance(orchestration_plan, dict):
        verify_cap = str(orchestration_plan.get("verify_with") or "").strip()
    if verify_cap and isinstance(collab, dict):
        known = list(collab.get("collaborates_with") or [])
        if verify_cap not in known and verify_cap != task_type:
            errors.append(f"verify_cap_not_in_collaboration_map:{verify_cap}")

    return AgentRuntimeVerification(ok=not errors, errors=errors)
