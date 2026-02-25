# iOS/macOS automation capability (stub)

def run(input_data: dict) -> dict:
    project = input_data.get("project")
    action = input_data.get("action")
    if not project or not action:
        return {"status": "error", "error": "project_action_required"}
    return {"status": "ok", "output": {"project": project, "action": action, "artifact": "pending"}}
