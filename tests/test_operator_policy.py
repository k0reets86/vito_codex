from modules.operator_policy import OperatorPolicy


def test_tool_policy_allow_deny(tmp_path):
    db = str(tmp_path / "operator.db")
    op = OperatorPolicy(sqlite_path=db)
    allowed, _ = op.is_tool_allowed("capability:research")
    assert allowed is True
    op.set_tool_policy("capability:research", enabled=False, notes="owner block")
    allowed, reason = op.is_tool_allowed("capability:research")
    assert allowed is False
    assert "owner block" in reason
    op.set_tool_policy("capability:research", enabled=True)
    allowed, reason = op.is_tool_allowed("capability:research")
    assert allowed is True
    assert reason == "operator_allow"


def test_budget_policy_hard_block(tmp_path):
    db = str(tmp_path / "operator.db")
    op = OperatorPolicy(sqlite_path=db)
    op.set_budget_policy("capability:research", daily_limit_usd=1.0, hard_block=True, notes="strict")
    # Simulate spend in last day
    conn = op._get_conn()
    try:
        conn.execute(
            "INSERT INTO data_lake_budget (agent, amount, category, description) VALUES (?, ?, ?, ?)",
            ("capability:research", 1.5, "api", "test"),
        )
        conn.commit()
    finally:
        conn.close()
    res = op.check_actor_budget("capability:research")
    assert res["allowed"] is False
    assert res["limit_usd"] == 1.0
