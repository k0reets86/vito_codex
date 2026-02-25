from modules.data_lake import DataLake


def test_data_lake_kpi_daily(tmp_path):
    db = str(tmp_path / "lake.db")
    dl = DataLake(sqlite_path=db)
    dl.record(agent="a1", task_type="t1", status="success", latency_ms=120, cost_usd=0.01)
    dl.record(agent="a1", task_type="t1", status="failed", latency_ms=80, cost_usd=0.0)
    trend = dl.kpi_daily(days=30)
    assert isinstance(trend, list)
    assert len(trend) >= 1
    row = trend[0]
    assert "date" in row
    assert "success_rate" in row
    assert "avg_latency_ms" in row
    assert "cost_usd" in row


def test_data_lake_handoff_methods(tmp_path):
    db = str(tmp_path / "lake2.db")
    dl = DataLake(sqlite_path=db)
    dl.record_handoff(
        from_agent="decision_loop",
        to_agent="research_agent",
        capability="research",
        step="analyze niche",
        status="success",
        goal_id="g1",
        trace_id="wf_1",
    )
    dl.record_handoff(
        from_agent="decision_loop",
        to_agent="research_agent",
        capability="research",
        step="analyze niche",
        status="failed",
        goal_id="g1",
        trace_id="wf_1",
    )
    rows = dl.recent_handoffs(limit=10)
    assert len(rows) >= 2
    assert rows[0]["to"] == "research_agent"
    summary = dl.handoff_summary(days=30)
    assert len(summary) >= 1
    s = summary[0]
    assert s["from"] == "decision_loop"
    assert s["to"] == "research_agent"
    assert s["total"] >= 2
