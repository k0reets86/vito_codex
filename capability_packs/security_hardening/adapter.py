# Security hardening capability (stub)

def run(input_data: dict) -> dict:
    policy = input_data.get("policy")
    if not policy:
        return {"status": "error", "error": "policy_required"}
    return {"status": "ok", "output": {"policy": policy, "report": "pending"}}
