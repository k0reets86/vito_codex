from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["scenario"])
    if missing:
        return error_result("scenario_required", capability="games_simulation", missing=missing)
    scenario = str(input_data.get("scenario") or "").strip()
    seed = str(input_data.get("seed") or "default")
    steps = list(input_data.get("steps") or ["setup", "playthrough", "score"])
    return success_result(
        "games_simulation",
        output={
            "scenario": scenario,
            "seed": seed,
            "result": "simulated",
            "metrics": {"steps": len(steps), "completion": 1.0},
            "recommended_actions": ["analyze_outcome", "compare_strategies"],
        },
        evidence={"id": f"sim:{scenario[:32]}:{seed}"},
        next_actions=["capture_metrics", "store_simulation_fact"],
        recovery_hints=["rerun_with_new_seed", "reduce_scenario_scope"],
    )
