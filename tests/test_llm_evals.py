from modules.llm_evals import LLMEvals


def test_llm_evals_compute_and_runs(tmp_path):
    db = str(tmp_path / "evals.db")
    ev = LLMEvals(sqlite_path=db)
    conn = ev._get_conn()
    try:
        conn.execute(
            "INSERT INTO spend_log (date, model, task_type, cost_usd) VALUES (date('now'), ?, ?, ?)",
            ("gpt-4o-strategic", "strategy", 2.5),
        )
        conn.execute(
            "INSERT INTO data_lake_events (agent, task_type, status) VALUES (?, ?, ?)",
            ("llm_router", "llm:strategy", "failed"),
        )
        conn.execute(
            "INSERT INTO llm_guardrail_events (event_type, task_type, blocked, reason) VALUES (?, ?, ?, ?)",
            ("prompt_injection", "strategy", 1, "prompt_injection_signals"),
        )
        conn.commit()
    finally:
        conn.close()

    current = ev.compute()
    assert "score" in current
    assert current["blocked_count_24h"] >= 1
    runs = ev.recent_runs(limit=5)
    assert runs
