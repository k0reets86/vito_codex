"""Боeвая матрица зрелости для всех 23 агентов VITO.

Phase M требует не только статуса `combat_ready`, но и повторяемой scorecard
по ключевым осям:
- autonomy
- data_usage
- evidence_quality
- collaboration_quality
- recovery_quality
"""

from __future__ import annotations

from typing import Any

from modules.agent_contracts import list_agent_contracts

AGENT_FAMILY_MAP: dict[str, str] = {
    "vito_core": "core_control",
    "quality_judge": "core_control",
    "hr_agent": "core_control",
    "trend_scout": "intelligence_research",
    "research_agent": "intelligence_research",
    "analytics_agent": "intelligence_research",
    "document_agent": "intelligence_research",
    "browser_agent": "commerce_execution",
    "account_manager": "commerce_execution",
    "ecommerce_agent": "commerce_execution",
    "publisher_agent": "commerce_execution",
    "content_creator": "content_growth",
    "seo_agent": "content_growth",
    "marketing_agent": "content_growth",
    "smm_agent": "content_growth",
    "email_agent": "content_growth",
    "translation_agent": "content_growth",
    "partnership_agent": "content_growth",
    "economics_agent": "content_growth",
    "legal_agent": "governance_resilience",
    "risk_agent": "governance_resilience",
    "security_agent": "governance_resilience",
    "devops_agent": "governance_resilience",
}


def _clamp10(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)


def _ratio(items: list[dict[str, Any]], key: str, truthy: bool = True) -> float:
    if not items:
        return 0.0
    count = 0
    for item in items:
        value = item.get(key)
        count += 1 if bool(value) is truthy else 0
    return count / len(items)


def _informative_error_ratio(runtime_rows: list[dict[str, Any]]) -> float:
    if not runtime_rows:
        return 0.0
    informative = 0
    for row in runtime_rows:
        err = str(row.get("error") or "").strip()
        if err and len(err) >= 12 and "unknown task_type" not in err.lower():
            informative += 1
    return informative / len(runtime_rows)


def _family_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "agents": 0,
            "autonomy": 0.0,
            "data_usage": 0.0,
            "evidence_quality": 0.0,
            "collaboration_quality": 0.0,
            "recovery_quality": 0.0,
            "total_score": 0.0,
        }
    keys = [
        "autonomy",
        "data_usage",
        "evidence_quality",
        "collaboration_quality",
        "recovery_quality",
        "total_score",
    ]
    out = {"agents": len(rows)}
    for key in keys:
        out[key] = round(sum(float(r["scorecard"][key]) for r in rows) / len(rows), 2)
    return out


def score_agent_row(row: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, float]:
    contract = dict(contract or {})
    runtime_rows = list(row.get("runtime") or [])
    static = dict(row.get("static") or {})

    runtime_success_ratio = _ratio(runtime_rows, "task_success")
    runtime_shape_ratio = _ratio(runtime_rows, "result_shape_ok")
    non_wrapper_ratio = _ratio(runtime_rows, "non_wrapper_path")
    informative_error_ratio = _informative_error_ratio(runtime_rows)

    static_score = float(static.get("score10") or 0.0)
    capabilities_count = float(len(row.get("capabilities") or []))
    tool_scope_count = float(len(contract.get("tool_scopes") or []))
    evidence_count = float(len(contract.get("required_evidence") or []))
    collaborator_count = float(len(contract.get("collaborates_with") or []))
    memory_input_count = float(len(contract.get("memory_inputs") or []))
    memory_output_count = float(len(contract.get("memory_outputs") or []))
    escalation_count = float(len(contract.get("escalation_rules") or []))
    workflow_roles = dict(contract.get("workflow_roles") or {})
    workflow_role_count = sum(len(v or []) for v in workflow_roles.values())
    runtime_enforced_bonus = 1.0 if contract.get("runtime_enforced") else 0.0

    autonomy = _clamp10((runtime_success_ratio * 6.0) + (non_wrapper_ratio * 2.0) + ((static_score / 10.0) * 2.0))
    data_usage = _clamp10(
        (min(tool_scope_count, 5.0) / 5.0) * 4.0
        + (min(capabilities_count, 6.0) / 6.0) * 2.0
        + (min(memory_input_count + memory_output_count, 8.0) / 8.0) * 2.0
        + (non_wrapper_ratio * 2.0)
    )
    evidence_quality = _clamp10(
        (runtime_shape_ratio * 4.0)
        + (runtime_success_ratio * 2.0)
        + (min(evidence_count, 4.0) / 4.0) * 2.0
        + runtime_enforced_bonus
        + (1.0 if contract.get("owned_outcomes") else 0.0)
    )
    collaboration_quality = _clamp10(
        (min(collaborator_count, 5.0) / 5.0) * 4.0
        + (min(workflow_role_count, 6.0) / 6.0) * 3.0
        + (non_wrapper_ratio * 3.0)
    )
    recovery_quality = _clamp10(
        (min(escalation_count, 3.0) / 3.0) * 2.0
        + (min(memory_output_count, 5.0) / 5.0) * 2.0
        + (informative_error_ratio * 3.0)
        + (1.5 if any(k in (contract.get("role") or "") for k in ["guard", "operator", "manager"]) else 0.0)
        + (1.5 if {"quality_judge", "devops_agent", "vito_core"} & set(contract.get("collaborates_with") or []) else 0.0)
    )
    total_score = _clamp10((autonomy + data_usage + evidence_quality + collaboration_quality + recovery_quality) / 5.0)
    return {
        "autonomy": autonomy,
        "data_usage": data_usage,
        "evidence_quality": evidence_quality,
        "collaboration_quality": collaboration_quality,
        "recovery_quality": recovery_quality,
        "total_score": total_score,
    }


def build_benchmark_matrix(megatest_report: dict[str, Any]) -> dict[str, Any]:
    contracts = list_agent_contracts()
    rows_in = list(megatest_report.get("rows") or [])
    rows_out: list[dict[str, Any]] = []
    families: dict[str, list[dict[str, Any]]] = {}

    for row in rows_in:
        agent = str(row.get("agent") or "").strip()
        contract = contracts.get(agent, {})
        family = AGENT_FAMILY_MAP.get(agent, "unclassified")
        scorecard = score_agent_row(row, contract)
        enriched = dict(row)
        enriched["family"] = family
        enriched["scorecard"] = scorecard
        rows_out.append(enriched)
        families.setdefault(family, []).append(enriched)

    family_rows = {
        family: _family_summary(items)
        for family, items in sorted(families.items())
    }
    total_score = round(sum(r["scorecard"]["total_score"] for r in rows_out) / len(rows_out), 2) if rows_out else 0.0
    return {
        "total_agents": len(rows_out),
        "families": family_rows,
        "rows": rows_out,
        "benchmark_matrix_score": total_score,
        "all_agents_scored": len(rows_out) == len(contracts),
    }
