from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["handoff"])
    if missing:
        return error_result("handoff_required", capability="agent_protocols", missing=missing)
    handoff = dict(input_data.get("handoff") or {})
    trace = {
        "from": str(handoff.get("from") or "unknown"),
        "to": str(handoff.get("to") or "unknown"),
        "task": str(handoff.get("task") or input_data.get("task") or "unknown"),
        "task_root_id": str(input_data.get("task_root_id") or handoff.get("task_root_id") or ""),
    }
    warnings = []
    if not trace["task_root_id"]:
        warnings.append("task_root_id_missing")
    return success_result(
        "agent_protocols",
        output={"result": "validated", "trace": trace, "handoff": handoff, "status": "validated"},
        evidence={"id": f"handoff:{trace['from']}->{trace['to']}:{trace['task']}"},
        next_actions=["dispatch_target_agent", "capture_handoff_result"],
        recovery_hints=["rebuild_handoff_contract", "attach_task_root_id"],
        warnings=warnings,
    )
