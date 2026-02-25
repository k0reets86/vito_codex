# Transport routing capability (stub)

def run(input_data: dict) -> dict:
    origin = input_data.get("origin")
    destination = input_data.get("destination")
    if not origin or not destination:
        return {"status": "error", "error": "origin_destination_required"}
    return {
        "status": "ok",
        "output": {
            "route": f"{origin} -> {destination}",
            "duration": "unknown",
            "cost": "unknown",
        },
    }
