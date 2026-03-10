from modules.evolution_archive import EvolutionArchive


def test_evolution_archive_record_and_summary(tmp_path):
    archive = EvolutionArchive(sqlite_path=str(tmp_path / "archive.db"))
    archive.record(
        archive_type="self_heal_v2",
        title="decision_loop:RuntimeError",
        payload={"ok": True},
        success=True,
        task_root_id="task-1",
    )
    archive.record(
        archive_type="self_evolve_v2",
        title="weekly_evolve_cycle",
        payload={"approved": False},
        success=False,
        task_root_id="task-2",
    )
    recent = archive.recent(limit=5)
    assert len(recent) == 2
    summary = archive.summary(limit=5)
    assert summary["total"] == 2
    assert summary["success"] == 1
    assert "self_heal_v2" in summary["by_type"]
