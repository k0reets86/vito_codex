"""Runtime responsibility graph and final enforcement for all 23 agents.

Phase N:
- lead/support/verify/block matrix in runtime
- block signals stop unsafe execution
- coverage audit for all required interactions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.agent_contracts import list_agent_contracts

TASK_WORKFLOW_MAP: dict[str, str] = {
    "trend_scan": "trend_pipeline",
    "niche_research": "trend_pipeline",
    "research": "research_pipeline",
    "competitor_analysis": "research_pipeline",
    "market_analysis": "research_pipeline",
    "content_creation": "content_pipeline",
    "article": "content_pipeline",
    "ebook": "content_pipeline",
    "product_turnkey": "content_pipeline",
    "listing_create": "publish_pipeline",
    "publish": "publish_pipeline",
    "publish_package_build": "publish_pipeline",
    "platform_rules_sync": "publish_pipeline",
    "social_media": "social_publish_pipeline",
    "campaign_plan": "social_publish_pipeline",
    "analytics": "analytics_pipeline",
    "forecast": "analytics_pipeline",
    "legal": "risk_pipeline",
    "copyright": "risk_pipeline",
    "gdpr": "risk_pipeline",
    "risk_assessment": "risk_pipeline",
    "security": "security_pipeline",
    "health_check": "runtime_maintenance_pipeline",
    "backup": "runtime_maintenance_pipeline",
    "agent_development": "agent_improvement_pipeline",
    "quality_review": "quality_gate_pipeline",
    "content_check": "quality_gate_pipeline",
    "browse": "browser_execution_pipeline",
    "form_fill": "browser_execution_pipeline",
    "account_management": "auth_pipeline",
    "email_code": "auth_pipeline",
}

_DEFAULT_BLOCK_OWNERS = ["quality_judge", "risk_agent", "security_agent", "vito_core"]
_BLOCK_ERROR_MARKERS = (
    "blocked",
    "policy_blocked",
    "budget_blocked",
    "auth_interrupt",
    "challenge_detected",
    "verification_failed",
    "runtime_contract_invalid",
    "contract_invalid",
    "unsafe_execution",
)


@dataclass
class ResponsibilityDecision:
    ok: bool
    workflow: str
    lead: list[str]
    support: list[str]
    verify: list[str]
    block: list[str]
    block_signals: list[str]
    reason: str = ""


def _workflow_map_from_contracts() -> dict[str, dict[str, list[str]]]:
    workflows: dict[str, dict[str, list[str]]] = {}
    for agent_name, contract in list_agent_contracts().items():
        roles = dict(contract.get("workflow_roles") or {})
        for role_name in ("lead", "support", "verify"):
            for workflow in roles.get(role_name, []) or []:
                if workflow == "all":
                    continue
                bucket = workflows.setdefault(workflow, {"lead": [], "support": [], "verify": [], "block": []})
                bucket[role_name].append(agent_name)
        bucket_names = set(contract.get("collaborates_with") or [])
        if {"quality_judge", "risk_agent", "security_agent", "vito_core"} & bucket_names:
            for workflow in roles.get("lead", []) or []:
                if workflow == "all":
                    continue
                wf = workflows.setdefault(workflow, {"lead": [], "support": [], "verify": [], "block": []})
                wf["block"].extend(sorted({"quality_judge", "risk_agent", "security_agent", "vito_core"} & bucket_names))
    for workflow, bucket in workflows.items():
        if not bucket["block"]:
            bucket["block"] = list(_DEFAULT_BLOCK_OWNERS)
        for key in list(bucket.keys()):
            bucket[key] = sorted(set(bucket[key]))
    return workflows


def build_responsibility_graph() -> dict[str, dict[str, list[str]]]:
    return _workflow_map_from_contracts()


def resolve_runtime_responsibility(task_type: str) -> dict[str, Any]:
    workflow = TASK_WORKFLOW_MAP.get(str(task_type or "").strip(), "")
    graph = build_responsibility_graph()
    bucket = graph.get(workflow, {"lead": [], "support": [], "verify": [], "block": list(_DEFAULT_BLOCK_OWNERS)})
    return {
        "task_type": str(task_type or "").strip(),
        "workflow": workflow,
        "lead": list(bucket.get("lead") or []),
        "support": list(bucket.get("support") or []),
        "verify": list(bucket.get("verify") or []),
        "block": list(bucket.get("block") or []),
    }


def detect_block_signals(result: Any) -> list[str]:
    signals: list[str] = []
    error = str(getattr(result, "error", "") or "").strip().lower()
    output = getattr(result, "output", None)
    metadata = getattr(result, "metadata", None)

    for marker in _BLOCK_ERROR_MARKERS:
        if marker in error:
            signals.append(marker)

    if isinstance(output, dict):
        status = str(output.get("status") or output.get("platform_status") or "").strip().lower()
        if status in {"blocked", "challenge_detected", "auth_interrupt"}:
            signals.append(status)
        if output.get("approved") is False:
            signals.append("judge_rejected")
        if output.get("blocked") is True:
            signals.append("blocked_flag")
    if isinstance(metadata, dict):
        verification = metadata.get("verification")
        if isinstance(verification, dict) and verification.get("approved") is False:
            signals.append("verification_rejected")
        if metadata.get("runtime_contract_ok") is False:
            signals.append("runtime_contract_invalid")
        if metadata.get("contract_ok") is False:
            signals.append("contract_invalid")
    return sorted(set(x for x in signals if x))


def enforce_responsibility_decision(task_type: str, result: Any) -> ResponsibilityDecision:
    runtime = resolve_runtime_responsibility(task_type)
    signals = detect_block_signals(result)
    if signals:
        return ResponsibilityDecision(
            ok=False,
            workflow=str(runtime.get("workflow") or ""),
            lead=list(runtime.get("lead") or []),
            support=list(runtime.get("support") or []),
            verify=list(runtime.get("verify") or []),
            block=list(runtime.get("block") or []),
            block_signals=signals,
            reason="blocked_by_runtime_signals",
        )
    return ResponsibilityDecision(
        ok=True,
        workflow=str(runtime.get("workflow") or ""),
        lead=list(runtime.get("lead") or []),
        support=list(runtime.get("support") or []),
        verify=list(runtime.get("verify") or []),
        block=list(runtime.get("block") or []),
        block_signals=[],
        reason="ok",
    )


def build_responsibility_coverage_audit() -> dict[str, Any]:
    contracts = list_agent_contracts()
    graph = build_responsibility_graph()
    workflows = sorted({w for w in graph.keys() if w})
    missing_verify = sorted([w for w, bucket in graph.items() if not list(bucket.get("verify") or [])])
    uncovered_agents = sorted([agent for agent in contracts.keys() if not any(agent in sum((bucket.get(k) or [] for k in ("lead", "support", "verify", "block")), []) for bucket in graph.values())])
    return {
        "total_agents": len(contracts),
        "all_agents_present": len(contracts) == 23,
        "workflow_count": len(workflows),
        "workflows": workflows,
        "missing_verify_workflows": missing_verify,
        "uncovered_agents": uncovered_agents,
        "coverage_ok": len(workflows) > 0 and not uncovered_agents,
    }
