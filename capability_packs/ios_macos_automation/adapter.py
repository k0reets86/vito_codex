from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["project", "action"])
    if missing:
        return error_result("project_action_required", capability="ios_macos_automation", missing=missing)
    project = str(input_data.get("project") or "").strip()
    action = str(input_data.get("action") or "").strip().lower()
    target = str(input_data.get("target") or "ios").strip().lower()
    return success_result(
        "ios_macos_automation",
        output={
            "project": project,
            "action": action,
            "target": target,
            "artifact": {"status": "prepared", "path": str(input_data.get("artifact_path") or "")},
            "logs": [f"prepared:{action}:{target}"],
        },
        evidence={"path": str(input_data.get("artifact_path") or "")},
        next_actions=["run_build", "capture_codesign_status"],
        recovery_hints=["switch_to_dry_run", "validate_project_path"],
    )
