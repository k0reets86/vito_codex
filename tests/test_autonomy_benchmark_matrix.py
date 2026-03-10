from modules.autonomy_benchmark_matrix import run_autonomy_matrix


def test_autonomy_benchmark_matrix_scores_all_agents():
    result = run_autonomy_matrix(
        curriculum={
            "goals": [{"title": "Goal 1"}],
            "state": {"active_goals": 2},
            "runtime_profile": {"skill_support": ["x"]},
            "used_skills": ["x"],
        },
        opportunity={
            "proposals": [{"title": "Idea", "expected_revenue": 100}],
            "runtime_profile": {"skill_support": ["y"]},
            "used_skills": ["y"],
        },
        self_evolver={
            "proposals": [{"title": "Improve", "proposal_score": 8.2}],
            "runtime_profile": {"proposal_count": 1},
            "archive_ref": "self_evolve_v2:benchmark_proposals",
            "used_skills": ["z"],
        },
    )
    assert result["all_agents_scored"] is True
    assert len(result["results"]) == 3
    assert result["average_score"] > 0
