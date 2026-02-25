import sqlite3
from pathlib import Path

from modules.final_scorecard import FinalScorecard


def test_final_scorecard_calculate(tmp_path: Path):
    db = str(tmp_path / "score.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE skills (id INTEGER PRIMARY KEY, name TEXT, description TEXT, success_count INTEGER, fail_count INTEGER, last_used TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE skill_registry (name TEXT PRIMARY KEY, tests_coverage REAL DEFAULT 0, compatibility TEXT DEFAULT 'stable', risk_score REAL DEFAULT 0, status TEXT, category TEXT, source TEXT, security_status TEXT, notes TEXT, version INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT, last_used TEXT, last_audit TEXT)"
    )
    conn.execute(
        "CREATE TABLE execution_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, status TEXT, detail TEXT, evidence TEXT, evidence_json TEXT, source TEXT, created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "CREATE TABLE failure_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, task_type TEXT, detail TEXT, error TEXT, created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "CREATE TABLE agent_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, task_type TEXT, status TEXT, output_json TEXT, error TEXT, created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "CREATE TABLE agent_playbooks (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, task_type TEXT, action TEXT, strategy_json TEXT, success_count INTEGER, fail_count INTEGER, last_status TEXT, updated_at TEXT)"
    )
    conn.execute("INSERT INTO skills(name) VALUES ('s1')")
    conn.execute("INSERT INTO skill_registry(name, tests_coverage) VALUES ('s1', 0.5)")
    conn.execute("INSERT INTO execution_facts(action,status,detail,evidence) VALUES ('platform:publish','published','gumroad x','http://x')")
    conn.execute("INSERT INTO failure_memory(agent) VALUES ('a')")
    conn.execute("INSERT INTO agent_feedback(agent) VALUES ('a')")
    conn.execute("INSERT INTO agent_playbooks(agent,task_type,action,success_count,fail_count,last_status) VALUES ('a','t','x',1,0,'success')")
    conn.commit()
    conn.close()

    data = FinalScorecard(sqlite_path=db).calculate()
    assert "avg" in data
    assert "blocks" in data
    assert len(data["blocks"]) == 7
    assert 0 <= data["avg"] <= 10
