from unittest.mock import MagicMock, patch

from modules.governance_reporter import GovernanceReporter


def test_governance_reporter_weekly_report_aggregates_sources():
    memory = MagicMock()
    memory.get_memory_policy_summary.return_value = {"quality_score": 0.8, "save_ratio": 0.75}
    memory.retention_drift_alerts.return_value = {"alerts": []}
    with patch("modules.governance_reporter.LLMEvals") as llm_cls, \
         patch("modules.governance_reporter.ToolingRegistry") as tr_cls, \
         patch("modules.governance_reporter.SkillRegistry") as sr_cls, \
         patch("modules.governance_reporter.ProviderHealth") as ph_cls:
        llm_cls.return_value.compute.return_value = {"score": 91, "fail_rate": 0.08, "cost_anomaly": False}
        tr_cls.return_value.build_governance_report.return_value = {"remediations": [], "pending_contract_rotations": 0}
        sr_cls.return_value.audit_summary.return_value = {"total": 3, "pending": 0, "high_risk": 0}
        sr_cls.return_value.remediate_high_risk.return_value = {"created": 0, "open_total": 0, "items": []}
        ph_cls.return_value.summary.return_value = {"overall_status": "ok", "remediations": []}

        report = GovernanceReporter(memory_manager=memory, sqlite_path=":memory:").weekly_report(days=7)

    assert report["status"] == "ok"
    assert report["window_days"] == 7
    assert report["llm"]["score"] == 91
    assert report["skill_audit"]["total"] == 3
    assert report["memory_summary"]["quality_score"] == 0.8
    assert report["remediations"] == []


def test_governance_reporter_marks_critical_on_llm_anomaly():
    memory = MagicMock()
    memory.get_memory_policy_summary.return_value = {"quality_score": 0.4, "save_ratio": 0.4}
    memory.retention_drift_alerts.return_value = {"alerts": [{"code": "low_quality"}]}
    with patch("modules.governance_reporter.LLMEvals") as llm_cls, \
         patch("modules.governance_reporter.ToolingRegistry") as tr_cls, \
         patch("modules.governance_reporter.SkillRegistry") as sr_cls, \
         patch("modules.governance_reporter.ProviderHealth") as ph_cls:
        llm_cls.return_value.compute.return_value = {"score": 41, "fail_rate": 0.42, "cost_anomaly": True}
        tr_cls.return_value.build_governance_report.return_value = {"remediations": ["Rotate keys"]}
        sr_cls.return_value.audit_summary.return_value = {"total": 10, "pending": 2, "high_risk": 1}
        sr_cls.return_value.remediate_high_risk.return_value = {"created": 1, "open_total": 3, "items": [{"skill_name": "s1"}]}
        ph_cls.return_value.summary.return_value = {"overall_status": "degraded", "remediations": ["Add keys"]}

        report = GovernanceReporter(memory_manager=memory, sqlite_path=":memory:").weekly_report(days=7)
        md = GovernanceReporter.to_markdown(report)

    assert report["status"] == "critical"
    assert report["remediations"]
    assert report["safe_action_suggestions"]
    assert "Weekly Governance Report" in md
    assert "Safe Actions" in md
    assert "Remediations" in md
    assert "Skills:" in md


def test_governance_reporter_safe_actions_rank_by_score():
    suggestions = GovernanceReporter._safe_action_suggestions(
        llm={"fail_rate": 0.31, "cost_anomaly": False},
        tooling={"key_rotation_health": {"alerts": ["a1", "a2", "a3", "a4"]}},
        providers={"overall_status": "ok"},
        memory_drift={"alerts": []},
        skill_audit={"pending": 0, "high_risk": 0},
        skill_remediation={"open_total": 0},
    )
    assert suggestions
    assert suggestions[0]["action"] == "disable_tooling_live"
    assert float(suggestions[0].get("score", 0) or 0) >= float(suggestions[-1].get("score", 0) or 0)


def test_governance_reporter_emits_extended_safe_actions():
    suggestions = GovernanceReporter._safe_action_suggestions(
        llm={"fail_rate": 0.41, "cost_anomaly": True},
        tooling={"key_rotation_health": {"alerts": ["a1", "a2", "a3"]}},
        providers={"overall_status": "ok"},
        memory_drift={"alerts": []},
        skill_audit={"pending": 0, "high_risk": 0},
        skill_remediation={"open_total": 0},
    )
    actions = {str(x.get("action") or "") for x in suggestions}
    assert "disable_discovery_intake" in actions
    assert "enable_revenue_dry_run" in actions


def test_governance_reporter_emits_disable_revenue_engine_on_critical_combination():
    suggestions = GovernanceReporter._safe_action_suggestions(
        llm={"fail_rate": 0.5, "cost_anomaly": True},
        tooling={"key_rotation_health": {"alerts": ["a1", "a2", "a3"]}},
        providers={"overall_status": "ok"},
        memory_drift={"alerts": []},
        skill_audit={"pending": 0, "high_risk": 0},
        skill_remediation={"open_total": 0},
    )
    assert suggestions
    assert suggestions[0]["action"] == "disable_revenue_engine"


def test_governance_reporter_emits_self_healer_and_self_learning_safety_actions():
    suggestions = GovernanceReporter._safe_action_suggestions(
        llm={"fail_rate": 0.44, "cost_anomaly": False},
        tooling={"key_rotation_health": {"alerts": []}},
        providers={"overall_status": "ok"},
        memory_drift={"alerts": []},
        skill_audit={"pending": 2, "high_risk": 1},
        skill_remediation={"open_total": 2},
    )
    actions = {str(x.get("action") or "") for x in suggestions}
    assert "tighten_self_healer_budget" in actions
    assert "pause_self_learning_autopromote" in actions
