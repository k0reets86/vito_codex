from modules.mem0_bridge import Mem0Bridge


class _FakeMem0:
    def __init__(self):
        self.added = []

    def add(self, text, user_id=None, metadata=None, collection_name=None):
        self.added.append((text, user_id, metadata, collection_name))

    def search(self, query=None, user_id=None, collection_name=None, limit=5):
        return [{"id": "m1", "text": f"mem0:{query}", "metadata": {"k": "v"}}]


def test_mem0_bridge_add_and_search(monkeypatch):
    backend = _FakeMem0()
    bridge = Mem0Bridge(backend=backend)
    bridge._enabled = True
    assert bridge.add("hello", {"doc_id": "x"}) is True
    rows = bridge.search("trend", limit=3)
    assert backend.added
    assert rows[0]["source"] == "mem0"
    assert rows[0]["text"] == "mem0:trend"
