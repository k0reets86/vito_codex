from modules.agent_benchmark_matrix import AGENT_FAMILY_MAP, build_benchmark_matrix
from modules.agent_contracts import list_agent_contracts


def test_agent_family_map_covers_all_contract_agents():
    contracts = list_agent_contracts()
    assert set(AGENT_FAMILY_MAP.keys()) == set(contracts.keys())


def test_build_benchmark_matrix_scores_all_agents():
    contracts = list_agent_contracts()
    rows = []
    for agent in sorted(contracts.keys()):
        rows.append(
            {
                "agent": agent,
                "capabilities": ["demo_capability"],
                "static": {"score10": 8},
                "runtime": [
                    {
                        "capability": "demo_capability",
                        "task_success": True,
                        "result_shape_ok": True,
                        "non_wrapper_path": True,
                        "error": "",
                    }
                ],
                "combat_ready": True,
            }
        )
    report = build_benchmark_matrix({"rows": rows})
    assert report["all_agents_scored"] is True
    assert report["total_agents"] == len(contracts)
    assert report["families"]
    assert 0.0 <= report["benchmark_matrix_score"] <= 10.0
    for row in report["rows"]:
        scorecard = row["scorecard"]
        for key in (
            "autonomy",
            "data_usage",
            "evidence_quality",
            "collaboration_quality",
            "recovery_quality",
            "total_score",
        ):
            assert 0.0 <= float(scorecard[key]) <= 10.0
