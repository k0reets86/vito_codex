from modules.platform_knowledge import record_platform_lesson
from modules.platform_runtime_registry import build_runtime_entry, get_runtime_entry, sync_platform_runtime_registry
from modules.platform_runbook_packs import build_service_runbook_pack
from modules.knowledge_consolidator import KnowledgeConsolidator


class _MemoryStub:
    def search_knowledge(self, query, n_results=5):
        return []


class _GraphStub:
    def neighbors(self, node_id, limit=5):
        return []


class _ReflectorStub:
    def top_relevant(self, query, n=5):
        return []


def test_runtime_registry_builds_runtime_entry():
    entry = build_runtime_entry('gumroad')
    assert entry['service'] == 'gumroad'
    assert 'required_artifacts' in entry
    assert 'policy_notes' in entry
    assert 'recommended_steps' in entry


def test_runtime_registry_refreshes_after_platform_lesson():
    record_platform_lesson(
        'etsy',
        status='draft',
        summary='Draft saved',
        details='File attached and images verified',
        lessons=['Verify after reload.'],
        anti_patterns=['Do not publish during tests.'],
        evidence={'file_attached': True, 'image_count': 3},
        source='test',
    )
    entry = get_runtime_entry('etsy', refresh=True)
    assert 'Verify after reload.' in entry['recommended_steps']
    assert 'Do not publish during tests.' in entry['avoid_patterns']
    assert 'file_attached' in entry['evidence_keys_seen']


def test_runbook_pack_uses_runtime_registry():
    sync_platform_runtime_registry(['etsy'])
    pack = build_service_runbook_pack('etsy')
    assert 'runtime_registry' in pack
    assert pack['policy_pack']['service'] == 'etsy'
    assert isinstance(pack['runtime_registry'], dict)


def test_knowledge_consolidator_includes_runtime_platform_entry():
    memory = _MemoryStub()
    consolidator = KnowledgeConsolidator(memory_manager=memory, reflector=_ReflectorStub())
    memory._knowledge_graph = _GraphStub()
    pack = consolidator.consolidate(query='etsy digital listing', services=['etsy'], limit=3)
    assert pack['platform_hits']
    first = pack['platform_hits'][0]
    assert first['service'] == 'etsy'
    assert 'runtime_entry' in first
    assert isinstance(first['runtime_entry'], dict)
