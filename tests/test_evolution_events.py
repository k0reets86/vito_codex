from modules.evolution_events import EvolutionEventStore


def test_evolution_event_store_roundtrip(tmp_path):
    db = tmp_path / 'events.db'
    store = EvolutionEventStore(sqlite_path=str(db))
    row = store.record_event(event_type='self_evolve', source='decision_loop', title='weekly', status='ok', payload={'n': 1})
    assert row['id'] > 0
    items = store.list_events(limit=10)
    assert items and items[0]['event_type'] == 'self_evolve'
    assert items[0]['payload']['n'] == 1
    summary = store.summary(days=7)
    assert summary['total'] >= 1
