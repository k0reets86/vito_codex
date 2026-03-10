import json

from modules.autonomy_proposals import AutonomyProposalStore


def test_autonomy_proposal_store_lifecycle(tmp_path):
    db = tmp_path / "test.sqlite"
    store = AutonomyProposalStore(sqlite_path=str(db))

    rows = store.upsert_batch(
        "opportunity_scout",
        "opportunity",
        [
            {"title": "Meme pack", "rationale": "fast trend", "expected_revenue": 120, "confidence": 0.81},
            {"title": "Creator bundle", "rationale": "broad demand", "expected_revenue": 90, "confidence": 0.74},
        ],
    )
    assert len(rows) == 2
    open_rows = store.list_open(limit=5)
    assert len(open_rows) == 2

    first = store.get_by_index(1, limit=5)
    assert first is not None
    proposal_id = int(first["proposal_id"])

    approved = store.mark_status(proposal_id, "approved", note="owner_approved")
    assert approved["status"] == "approved"

    executed = store.mark_status(proposal_id, "executed", note="goal_created")
    assert executed["status"] == "executed"
    assert "goal_created" in str(executed.get("execution_notes") or "")

    recent = store.list_recent(limit=5)
    assert any(int(item["proposal_id"]) == proposal_id for item in recent)


def test_autonomy_proposal_store_upsert_deduplicates(tmp_path):
    db = tmp_path / "test.sqlite"
    store = AutonomyProposalStore(sqlite_path=str(db))
    payload = [{"title": "Stable idea", "rationale": "x", "confidence": 0.6}]
    store.upsert_batch("curriculum_agent", "goal", payload)
    store.upsert_batch("curriculum_agent", "goal", payload)
    recent = store.list_recent(limit=10)
    assert len(recent) == 1
