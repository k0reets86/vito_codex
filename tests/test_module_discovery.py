from modules.module_discovery import ModuleDiscovery


def test_module_discovery_scoring_and_tags():
    d = ModuleDiscovery()
    score = d._score('agent-memory', 'browser workflow memory helper', 'browser memory')
    tags = d._tags('agent-memory', 'browser workflow memory helper')
    assert score >= 0.5
    assert 'browser' in tags
    assert 'memory' in tags
