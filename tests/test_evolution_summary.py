from __future__ import annotations

from modules.evolution_archive import EvolutionArchive
from modules.evolution_audit import EvolutionAuditTrail
from modules.evolution_events import EvolutionEventStore
from modules.evolution_summary import EvolutionSummaryBuilder


def test_evolution_summary_builder(tmp_path):
    db_path = tmp_path / "ae5.db"
    events = EvolutionEventStore(sqlite_path=str(db_path))
    audit = EvolutionAuditTrail(sqlite_path=str(db_path))
    archive = EvolutionArchive(sqlite_path=str(db_path))

    events.record_event(event_type="weekly_evolve_cycle", source="test", status="ok", title="weekly", payload={"k": 1})
    audit.record(event_type="apply_success", snapshot_id="s1", files=["a.py"], success=True, details="ok")
    archive.record(archive_type="evolve", title="Improve planner", payload={"score": 0.9}, success=True)

    builder = EvolutionSummaryBuilder(sqlite_path=str(db_path))
    payload = builder.build_owner_summary(days=30)
    markdown = builder.render_markdown(payload)

    assert payload["events"]["total"] >= 1
    assert "weekly_evolve_cycle" in markdown
    assert "Improve planner" in markdown
