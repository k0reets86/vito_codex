# Health & fitness capability (non-medical stub)

def run(input_data: dict) -> dict:
    metric = input_data.get("metric")
    value = input_data.get("value")
    if not metric or value is None:
        return {"status": "error", "error": "metric_value_required"}
    return {"status": "ok", "output": {"metric": metric, "value": value, "summary": "recorded"}}
