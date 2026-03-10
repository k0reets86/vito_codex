from modules.ops_runtime import build_devops_runtime_profile, build_security_runtime_profile


def test_build_devops_runtime_profile():
    out = build_devops_runtime_profile(operation="backup", success=True, issue_count=0, can_auto_remediate=False)
    assert out["operation"] == "backup"
    assert out["success"] is True
    assert "log_ops_evidence" in out["next_actions"]


def test_build_security_runtime_profile_block():
    out = build_security_runtime_profile(
        operation="audit_keys",
        risk_score=3,
        missing_count=2,
        weak_count=1,
        block_recommended=True,
    )
    assert out["block_recommended"] is True
    assert "open_security_block" in out["next_actions"]
