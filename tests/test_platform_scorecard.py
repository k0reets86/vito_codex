import sqlite3

from modules.platform_scorecard import PlatformScorecard


def test_platform_scorecard_basic(tmp_path):
    db = str(tmp_path / "score.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE execution_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT, status TEXT, detail TEXT, evidence TEXT, evidence_json TEXT, source TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO execution_facts(action,status,detail,evidence,source) VALUES (?,?,?,?,?)",
        ("platform:publish", "published", "gumroad sig=abc", "https://x", "gumroad.publish"),
    )
    conn.execute(
        "INSERT INTO execution_facts(action,status,detail,evidence,source) VALUES (?,?,?,?,?)",
        ("platform:publish", "error", "gumroad sig=def", "", "gumroad.publish"),
    )
    conn.commit()
    conn.close()

    sc = PlatformScorecard(sqlite_path=db)
    rows = sc.score(["gumroad"], days=30)
    assert len(rows) == 1
    r = rows[0]
    assert r["platform"] == "gumroad"
    assert r["success_count_30d"] >= 1
    assert r["fail_count_30d"] >= 1
    assert 0 <= r["readiness_score"] <= 100
