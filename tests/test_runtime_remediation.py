from pathlib import Path

from modules.runtime_remediation import (
    apply_safe_action,
    get_safe_action_trust,
    plan_safe_action_updates,
    rank_safe_action_suggestions,
    record_safe_action_outcome,
    suggest_safe_actions_for_failure,
)


def test_apply_safe_action_rejects_unknown(tmp_path):
    env_path = tmp_path / ".env"
    out = apply_safe_action("unknown_action", env_path=str(env_path))
    assert out == {}


def test_apply_safe_action_updates_env_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("NOTIFY_MODE=all\n", encoding="utf-8")
    out = apply_safe_action("set_notify_minimal", env_path=str(env_path))
    assert out.get("NOTIFY_MODE") == "minimal"
    text = env_path.read_text(encoding="utf-8")
    assert "NOTIFY_MODE=minimal" in text


def test_plan_safe_action_updates():
    out = plan_safe_action_updates("disable_tooling_live")
    assert out == {"TOOLING_RUN_LIVE_ENABLED": "false"}


def test_plan_safe_action_updates_new_playbooks():
    assert plan_safe_action_updates("disable_discovery_intake") == {"TOOLING_DISCOVERY_ENABLED": "false"}
    assert plan_safe_action_updates("enable_revenue_dry_run") == {"REVENUE_ENGINE_DRY_RUN": "true"}
    assert plan_safe_action_updates("disable_revenue_engine") == {"REVENUE_ENGINE_ENABLED": "false", "REVENUE_ENGINE_DRY_RUN": "true"}
    assert plan_safe_action_updates("tighten_self_healer_budget") == {"SELF_HEALER_MAX_CHANGED_FILES": "5", "SELF_HEALER_MAX_CHANGED_LINES": "300"}
    assert plan_safe_action_updates("pause_self_learning_autopromote") == {"SELF_LEARNING_AUTO_PROMOTE": "false"}


def test_apply_safe_action_noop_when_already_applied(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("NOTIFY_MODE=minimal\n", encoding="utf-8")
    monkeypatch.setenv("NOTIFY_MODE", "minimal")
    out = apply_safe_action("set_notify_minimal", env_path=str(env_path))
    assert out == {}


def test_safe_action_trust_metrics_are_persisted(tmp_path):
    sqlite_path = str(tmp_path / "remediation.db")
    record_safe_action_outcome("set_notify_minimal", "applied", sqlite_path=sqlite_path)
    record_safe_action_outcome("set_notify_minimal", "applied", sqlite_path=sqlite_path)
    record_safe_action_outcome("set_notify_minimal", "failed", sqlite_path=sqlite_path)
    record_safe_action_outcome("set_notify_minimal", "noop", sqlite_path=sqlite_path)

    trust = get_safe_action_trust("set_notify_minimal", sqlite_path=sqlite_path)
    assert trust["action"] == "set_notify_minimal"
    assert trust["total"] == 4
    assert trust["applied"] == 2
    assert trust["failed"] == 1
    assert trust["noop"] == 1
    assert trust["success_rate"] == 0.5


def test_rank_safe_action_suggestions_uses_trust_bias(tmp_path):
    sqlite_path = str(tmp_path / "remediation.db")
    for _ in range(4):
        record_safe_action_outcome("set_notify_minimal", "applied", sqlite_path=sqlite_path)
    for _ in range(3):
        record_safe_action_outcome("disable_tooling_live", "failed", sqlite_path=sqlite_path)

    ranked = rank_safe_action_suggestions(
        [
            {"action": "disable_tooling_live", "score": 8, "priority": 1},
            {"action": "set_notify_minimal", "score": 8, "priority": 2},
        ],
        sqlite_path=sqlite_path,
        days=30,
    )
    assert ranked[0]["action"] == "set_notify_minimal"
    assert float(ranked[0]["effective_score"]) > float(ranked[1]["effective_score"])


def test_record_safe_action_outcome_persists_context(tmp_path):
    sqlite_path = str(tmp_path / "remediation.db")
    record_safe_action_outcome(
        "pause_self_learning_autopromote",
        "applied",
        reason="candidate instability",
        source_agent="vito_core",
        task_family="research",
        source="self_healer",
        sqlite_path=sqlite_path,
    )
    import sqlite3
    conn = sqlite3.connect(sqlite_path)
    row = conn.execute(
        "SELECT source_agent, task_family, source FROM runtime_remediation_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ("vito_core", "research", "self_healer")


def test_suggest_safe_actions_for_failure_returns_relevant_actions():
    ranked = suggest_safe_actions_for_failure(
        agent="vito_core",
        error_type="RuntimeError",
        message="self_learning candidate auto_promote flaky and rate limit 429",
        context={"task_family": "research"},
    )
    actions = [x["action"] for x in ranked]
    assert "pause_self_learning_autopromote" in actions
    assert "apply_profile_economy" in actions
