"""Wave E/F readiness helpers: stealth posture + finance guardrails snapshot."""

from __future__ import annotations

from typing import Any


def build_stealth_readiness(
    *,
    browser_runtime_available: bool,
    cdp_adapter_enabled: bool,
    anti_detection_policy_enabled: bool,
    legal_gate_enabled: bool,
) -> dict[str, Any]:
    checks = {
        "browser_runtime_available": bool(browser_runtime_available),
        "cdp_adapter_enabled": bool(cdp_adapter_enabled),
        "anti_detection_policy_enabled": bool(anti_detection_policy_enabled),
        "legal_gate_enabled": bool(legal_gate_enabled),
    }
    passed = sum(1 for v in checks.values() if v)
    score = round((passed / float(len(checks))) * 100.0, 2)
    if score >= 100:
        status = "ready"
    elif score >= 50:
        status = "partial"
    else:
        status = "blocked"
    blockers = [k for k, v in checks.items() if not v]
    return {
        "status": status,
        "score": score,
        "checks": checks,
        "blockers": blockers,
    }


def build_finance_guardrail_snapshot(
    *,
    daily_spent_usd: float,
    daily_earned_usd: float,
    daily_limit_usd: float,
    net_profit_usd: float,
) -> dict[str, Any]:
    spent = max(0.0, float(daily_spent_usd or 0.0))
    earned = max(0.0, float(daily_earned_usd or 0.0))
    limit = max(0.01, float(daily_limit_usd or 0.01))
    net = float(net_profit_usd or 0.0)
    spend_ratio = round(spent / limit, 4)
    if spend_ratio >= 1.0:
        status = "critical"
    elif spend_ratio >= 0.8 or net < 0:
        status = "warning"
    else:
        status = "ok"
    return {
        "status": status,
        "daily_spent_usd": round(spent, 4),
        "daily_earned_usd": round(earned, 4),
        "daily_limit_usd": round(limit, 4),
        "spend_ratio": spend_ratio,
        "net_profit_usd": round(net, 4),
    }
