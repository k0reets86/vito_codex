# Smart home IoT capability (stub)

def run(input_data: dict) -> dict:
    device_id = input_data.get("device_id")
    action = input_data.get("action")
    if not device_id or not action:
        return {"status": "error", "error": "device_action_required"}
    return {"status": "ok", "output": {"device_id": device_id, "action": action, "status": "queued"}}
