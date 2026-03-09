from agents.base_agent import TaskResult
from modules.agent_responsibility_graph import (
    build_responsibility_coverage_audit,
    build_responsibility_graph,
    detect_block_signals,
    enforce_responsibility_decision,
    resolve_runtime_responsibility,
)


def test_responsibility_graph_has_workflows_and_coverage():
    graph = build_responsibility_graph()
    assert "publish_pipeline" in graph
    assert "quality_gate_pipeline" in graph
    audit = build_responsibility_coverage_audit()
    assert audit["all_agents_present"] is True
    assert audit["coverage_ok"] is True
    assert audit["workflow_count"] > 0


def test_detect_block_signals_from_runtime_contract_error():
    result = TaskResult(
        success=False,
        error="runtime_contract_invalid:missing_required_evidence:url",
        metadata={"runtime_contract_ok": False},
    )
    signals = detect_block_signals(result)
    assert "runtime_contract_invalid" in signals


def test_enforce_responsibility_blocks_unsafe_result():
    result = TaskResult(success=True, output={"status": "blocked"})
    decision = enforce_responsibility_decision("listing_create", result)
    assert decision.ok is False
    assert "blocked" in decision.block_signals


def test_resolve_runtime_responsibility_for_publish_has_lead_and_block():
    runtime = resolve_runtime_responsibility("listing_create")
    assert runtime["workflow"] == "publish_pipeline"
    assert runtime["lead"]
    assert runtime["block"]
