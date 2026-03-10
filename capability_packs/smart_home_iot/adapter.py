from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["device_id", "action"])
    if missing:
        return error_result("device_action_required", capability="smart_home_iot", missing=missing)
    device_id = str(input_data.get("device_id") or "").strip()
    action = str(input_data.get("action") or "").strip().lower()
    value = input_data.get("value")
    return success_result(
        "smart_home_iot",
        output={
            "device_id": device_id,
            "action": action,
            "value": value,
            "status": "queued",
            "event_id": f"iot:{device_id}:{action}",
        },
        evidence={"id": f"iot:{device_id}:{action}"},
        next_actions=["dispatch_device_command", "verify_device_state"],
        recovery_hints=["poll_device_status", "fallback_to_manual_override"],
    )
