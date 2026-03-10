from modules.content_experiments import ContentExperimentEngine


def test_content_experiment_create_record_choose(tmp_path):
    db = tmp_path / "ab.db"
    engine = ContentExperimentEngine(sqlite_path=str(db))
    exp = engine.create_experiment(
        family="marketing_copy",
        subject="Planner",
        platform="facebook",
        variants=["Variant A", "Variant B", "Variant C"],
    )
    assert exp["status"] == "open"
    outcome_a = engine.record_outcome(exp["experiment_id"], "v1", impressions=100, clicks=10, conversions=3)
    outcome_b = engine.record_outcome(exp["experiment_id"], "v2", impressions=100, clicks=15, conversions=1)
    assert outcome_a["score"] != outcome_b["score"]
    winner = engine.choose_winner(exp["experiment_id"])
    assert winner["winner_variant"] in {"v1", "v2", "v3"}
    assert winner["winner_text"]
