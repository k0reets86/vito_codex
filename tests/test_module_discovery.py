from modules.module_discovery import ModuleDiscovery
import io
import json


def test_module_discovery_scoring_and_tags():
    d = ModuleDiscovery()
    score = d._score('agent-memory', 'browser workflow memory helper', 'browser memory')
    tags = d._tags('agent-memory', 'browser workflow memory helper')
    assert score >= 0.5
    assert 'browser' in tags
    assert 'memory' in tags


def test_module_discovery_pypi_json_path(monkeypatch):
    payload = {"info": {"name": "browser-memory", "summary": "Browser memory workflow helper", "package_url": "https://pypi.org/project/browser-memory/"}}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    d = ModuleDiscovery()
    rows = d.discover_pypi("browser memory", limit=1)
    assert rows
    assert rows[0]["source"] == "pypi"
    assert rows[0]["name"] == "browser-memory"
