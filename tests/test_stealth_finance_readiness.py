from modules.stealth_finance_readiness import (
    build_finance_guardrail_snapshot,
    build_stealth_readiness,
)


def test_build_stealth_readiness_ready():
    out = build_stealth_readiness(
        browser_runtime_available=True,
        cdp_adapter_enabled=True,
        anti_detection_policy_enabled=True,
        legal_gate_enabled=True,
    )
    assert out["status"] == "ready"
    assert out["score"] == 100.0
    assert out["blockers"] == []


def test_build_stealth_readiness_partial_with_blockers():
    out = build_stealth_readiness(
        browser_runtime_available=True,
        cdp_adapter_enabled=False,
        anti_detection_policy_enabled=False,
        legal_gate_enabled=True,
    )
    assert out["status"] == "partial"
    assert out["score"] == 50.0
    assert "cdp_adapter_enabled" in out["blockers"]
    assert "anti_detection_policy_enabled" in out["blockers"]


def test_build_finance_guardrail_snapshot_warning_on_negative_profit():
    out = build_finance_guardrail_snapshot(
        daily_spent_usd=6.0,
        daily_earned_usd=2.0,
        daily_limit_usd=10.0,
        net_profit_usd=-4.0,
    )
    assert out["status"] == "warning"
    assert out["spend_ratio"] == 0.6
    assert out["net_profit_usd"] == -4.0


def test_build_finance_guardrail_snapshot_critical_on_budget_overrun():
    out = build_finance_guardrail_snapshot(
        daily_spent_usd=12.0,
        daily_earned_usd=1.0,
        daily_limit_usd=10.0,
        net_profit_usd=-11.0,
    )
    assert out["status"] == "critical"
    assert out["spend_ratio"] == 1.2
