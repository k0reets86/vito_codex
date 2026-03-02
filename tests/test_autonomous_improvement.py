from modules.autonomous_improvement import AutonomousImprovementEngine


def test_generate_candidates_from_governance_and_self_learning(tmp_path):
    db = str(tmp_path / "auto_improve.db")
    engine = AutonomousImprovementEngine(sqlite_path=db)
    out = engine.generate_candidates(
        governance={
            "status": "critical",
            "safe_action_suggestions": [
                {"action": "enable_guardrails_block", "priority": 1, "score": 8, "reason": "high fail-rate"},
            ],
        },
        self_learning_summary={"open_test_jobs": 2, "pending_candidates": 1},
        limit=5,
    )
    assert int(out.get("created", 0) or 0) >= 2
    rows = engine.list_actions(status="open", limit=20)
    actions = {str(r.get("action") or "") for r in rows}
    assert "enable_guardrails_block" in actions
    assert "run_self_learning_test_jobs" in actions


def test_generate_candidates_deduplicates_recent_open(tmp_path):
    db = str(tmp_path / "auto_improve_dedup.db")
    engine = AutonomousImprovementEngine(sqlite_path=db)
    first = engine.generate_candidates(
        governance={
            "status": "warning",
            "safe_action_suggestions": [
                {"action": "set_notify_minimal", "priority": 2, "score": 4, "reason": "noise"},
            ],
        },
        self_learning_summary={},
        limit=3,
    )
    second = engine.generate_candidates(
        governance={
            "status": "warning",
            "safe_action_suggestions": [
                {"action": "set_notify_minimal", "priority": 2, "score": 4, "reason": "noise"},
            ],
        },
        self_learning_summary={},
        limit=3,
    )
    assert int(first.get("created", 0) or 0) == 1
    assert int(second.get("created", 0) or 0) == 0
