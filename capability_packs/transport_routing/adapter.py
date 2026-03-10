from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["origin", "destination"])
    if missing:
        return error_result("origin_destination_required", capability="transport_routing", missing=missing)
    origin = str(input_data.get("origin") or "").strip()
    destination = str(input_data.get("destination") or "").strip()
    mode = str(input_data.get("mode") or "multimodal").strip().lower()
    route = f"{origin} -> {destination}"
    return success_result(
        "transport_routing",
        output={
            "route": route,
            "mode": mode,
            "duration": str(input_data.get("duration") or "estimated"),
            "cost": str(input_data.get("cost") or "estimated"),
            "waypoints": list(input_data.get("waypoints") or []),
        },
        evidence={"id": f"route:{origin[:20]}:{destination[:20]}"},
        next_actions=["evaluate_alternative_routes", "confirm_constraints"],
        recovery_hints=["fallback_to_single_mode", "request_time_window"],
    )
