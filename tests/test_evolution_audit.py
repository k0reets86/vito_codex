from modules.evolution_audit import EvolutionAuditTrail


def test_evolution_audit_signatures_verify(tmp_path):
    db = tmp_path / 'audit.db'
    trail = EvolutionAuditTrail(sqlite_path=str(db), secret='secret')
    row = trail.record(event_type='apply_success', snapshot_id='snap1', files=['a.py'], success=True, details='ok')
    assert row['signature']
    items = trail.list_entries(limit=10)
    assert items and items[0]['signature_ok'] is True
