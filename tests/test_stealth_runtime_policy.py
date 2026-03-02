from modules.stealth_runtime_policy import StealthRuntimePolicy


def test_stealth_runtime_policy_gate_blocks_without_owner_approval():
    out = StealthRuntimePolicy.evaluate_gate(
        cdp_enabled=True,
        legal_gate_enabled=True,
        owner_approved=False,
    )
    assert out["allowed"] is False
    assert out["blocked"] is True
    assert out["reason"] == "owner_approval_required"


def test_stealth_runtime_policy_gate_allows_when_all_gates_pass():
    out = StealthRuntimePolicy.evaluate_gate(
        cdp_enabled=True,
        legal_gate_enabled=True,
        owner_approved=True,
    )
    assert out["allowed"] is True
    assert out["blocked"] is False
    assert out["reason"] == "ok"


def test_stealth_runtime_policy_summary_counts_events(tmp_path):
    pol = StealthRuntimePolicy(sqlite_path=str(tmp_path / "stealth.db"))
    pol.record_event(risk_score=0.7, blocked=False, reason="ok")
    pol.record_event(risk_score=0.4, blocked=True, reason="owner_approval_required")
    out = pol.summary(days=7)
    assert out["total_events"] == 2
    assert out["blocked_events"] == 1
    assert out["blocked_rate"] == 0.5
