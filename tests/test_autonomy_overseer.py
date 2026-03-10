from modules.autonomy_overseer import AutonomyOverseer
from modules.autonomy_proposals import AutonomyProposalStore


def test_autonomy_overseer_detects_stuck_session_and_stale_proposal(tmp_path):
    db = tmp_path / 'auto.db'
    store = AutonomyProposalStore(sqlite_path=str(db))
    rows = store.upsert_batch('curriculum_agent', 'goal', [{'title': 'Learn X', 'why': 'because'}])
    assert rows
    overseer = AutonomyOverseer(stuck_tick_threshold=10)
    report = overseer.inspect(
        tick_count=25,
        proposal_store=store,
        workflow_sessions=[{'goal_id': 'g1', 'state': 'running', 'last_tick': 10}],
    )
    assert report['finding_count'] >= 1
    assert any(x['type'] == 'workflow_stuck' for x in report['findings'])
