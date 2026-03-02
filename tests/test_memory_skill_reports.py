import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules.memory_skill_reports import MemorySkillReporter


@pytest.fixture
def retention_summary() -> dict:
    return {
        "total_events": 12,
        "saved": 8,
        "forgotten": 4,
        "quality_score": 0.78,
        "save_ratio": 0.66,
        "saved_by_retention": [{"project_mid": 6}, {"owner_long": 2}],
    }


def test_generate_markdown_report(tmp_path, retention_summary):
    memory = MagicMock()
    memory.get_memory_policy_summary.return_value = retention_summary
    memory.retention_drift_alerts.return_value = {"alerts": [{"code": "low_quality", "message": "Quality low", "severity": "low"}]}
    block = {
        "doc_id": "skill_block_sample_skill",
        "metadata_json": json.dumps({"skill_name": "sample_skill", "success_rate": 0.92}),
        "stage": "long",
        "importance": 0.9,
        "priority": 0.95,
        "updated_at": "2026-02-25T10:00:00Z",
    }
    block_store = MagicMock()
    block_store.blocks_by_type.return_value = [block]
    memory.memory_blocks = block_store
    registry = MagicMock()
    registry.get_skill.return_value = {"tests_coverage": 0.8, "risk_score": 0.2, "acceptance_status": "accepted"}

    reporter = MemorySkillReporter(memory_manager=memory, skill_registry=registry)
    markdown = reporter.generate_markdown_report(days=7, per_skill_limit=1)

    assert "Weekly Memory Report" in markdown
    assert "| sample_skill |" in markdown
    assert "low_quality" in markdown
    path = tmp_path / "weekly.md"
    result_path = reporter.persist_markdown(path, days=7, per_skill_limit=0)
    assert result_path == path
    assert path.exists()
    content = path.read_text()
    assert "Weekly Memory Report" in content
    assert "Learning Health" in markdown


def test_per_skill_quality_includes_self_learning_linkage(tmp_path, retention_summary):
    db = tmp_path / "mem_skill.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS self_learning_promotion_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                decision TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS self_learning_test_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                task_family TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                status TEXT DEFAULT 'open',
                attempts INTEGER DEFAULT 0,
                flaky INTEGER DEFAULT 0,
                result_notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            "INSERT INTO self_learning_promotion_events (skill_name, decision, reason, created_at) VALUES ('sample_skill', 'promoted', 'ok', datetime('now'))"
        )
        conn.execute(
            "INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, flaky, updated_at) VALUES ('sample_skill', 'research', 'seed', 'passed', 0, datetime('now'))"
        )
        conn.commit()
    finally:
        conn.close()

    memory = MagicMock()
    memory.get_memory_policy_summary.return_value = retention_summary
    memory.retention_drift_alerts.return_value = {"alerts": []}
    block = {
        "doc_id": "skill_block_sample_skill",
        "metadata_json": json.dumps({"skill_name": "sample_skill", "success_rate": 0.9}),
        "stage": "long",
        "importance": 0.9,
        "priority": 0.95,
        "updated_at": "2026-02-25T10:00:00Z",
    }
    block_store = MagicMock()
    block_store.blocks_by_type.return_value = [block]
    memory.memory_blocks = block_store
    registry = MagicMock()
    registry.get_skill.return_value = {"tests_coverage": 0.8, "risk_score": 0.2, "acceptance_status": "accepted"}

    reporter = MemorySkillReporter(memory_manager=memory, skill_registry=registry, sqlite_path=str(db))
    rows = reporter.per_skill_quality(limit=1)
    assert rows
    assert rows[0]["skill_name"] == "sample_skill"
    assert rows[0]["promotion_rate_45d"] == pytest.approx(1.0, rel=1e-6)
    assert rows[0]["flaky_rate_45d"] == pytest.approx(0.0, rel=1e-6)
    assert rows[0]["learning_health"] > 0.7
