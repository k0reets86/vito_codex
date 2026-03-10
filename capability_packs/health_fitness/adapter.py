from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["metric", "value"])
    if missing:
        return error_result("metric_value_required", capability="health_fitness", missing=missing)
    metric = str(input_data.get("metric") or "").strip().lower()
    value = input_data.get("value")
    timestamp = str(input_data.get("timestamp") or "runtime")
    return success_result(
        "health_fitness",
        output={
            "record_id": f"{metric}:{timestamp}",
            "metric": metric,
            "value": value,
            "summary": f"Recorded {metric}={value}",
            "classification": "non_medical_tracking",
        },
        evidence={"id": f"metric:{metric}:{timestamp}"},
        next_actions=["store_tracking_event", "review_trendline"],
        recovery_hints=["validate_units", "request_timestamp"],
    )
