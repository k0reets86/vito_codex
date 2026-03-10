from modules.memory_consolidation import MemoryConsolidationEngine


class _DummyMemory:
    def __init__(self):
        self._promoted = 0

    def cleanup_expired_memory(self, limit=0, dry_run=True):
        return {"expired_found": 2 if dry_run else 0, "deleted": 0}

    def retention_drift_alerts(self, days=30):
        return {"alerts": ["ttl_drift"]}

    def consolidate_short_term_memory(self, min_age_days=5, limit=25):
        self._promoted += 3
        return 3


def test_memory_consolidation_cycle_records_run(tmp_path):
    db = tmp_path / "mem.db"
    engine = MemoryConsolidationEngine(_DummyMemory(), sqlite_path=str(db))
    result = engine.run_cycle()
    assert result["promoted"] == 3
    assert result["expired_preview"] == 2
    latest = engine.latest_run()
    assert latest is not None
    assert latest["status"] in {"warning", "promoted", "backlog", "clean"}
