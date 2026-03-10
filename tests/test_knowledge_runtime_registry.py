from modules.knowledge_runtime_registry import load_knowledge_runtime_registry, record_knowledge_runtime_pack


def test_record_knowledge_runtime_pack_persists(tmp_path, monkeypatch):
    import modules.knowledge_runtime_registry as krr

    monkeypatch.setattr(krr, '_REGISTRY', tmp_path / 'knowledge_runtime_registry.json')
    key = record_knowledge_runtime_pack(
        query='etsy listing proof',
        services=['etsy'],
        task_root_id='task-1',
        pack={'summary': 'ok', 'confidence': 0.7},
    )
    data = load_knowledge_runtime_registry()
    assert key in data['entries']
    row = data['entries'][key]
    assert row['task_root_id'] == 'task-1'
    assert row['pack']['confidence'] == 0.7
