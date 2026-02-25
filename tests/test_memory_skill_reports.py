import json
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
