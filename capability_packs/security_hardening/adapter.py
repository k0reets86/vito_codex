from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["policy"])
    if missing:
        return error_result("policy_required", capability="security_hardening", missing=missing)
    policy = str(input_data.get("policy") or "").strip()
    context = dict(input_data.get("context") or {})
    actions = list(input_data.get("actions") or ["scan_secrets", "review_permissions", "verify_guardrails"])
    return success_result(
        "security_hardening",
        output={
            "policy": policy,
            "report": {"status": "prepared", "controls": len(actions), "context": context},
            "actions": actions,
            "risk_band": str(input_data.get("risk_band") or "medium"),
        },
        evidence={"id": f"security:{policy.lower().replace(' ', '_')[:40]}"},
        next_actions=["execute_checks", "escalate_blockers"],
        recovery_hints=["tighten_policy_scope", "rerun_with_system_context"],
    )
