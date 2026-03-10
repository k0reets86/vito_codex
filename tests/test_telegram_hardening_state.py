from modules.cancel_state import CancelState
from modules.conversation_memory import ConversationMemory
import json


def test_cancel_state_persists_between_instances(tmp_path):
    path = tmp_path / "cancel_state.json"
    c1 = CancelState(path=path)
    assert c1.is_cancelled() is False
    c1.cancel("owner_cancelled")
    assert c1.is_cancelled() is True

    c2 = CancelState(path=path)
    assert c2.is_cancelled() is True
    c2.clear()
    assert c2.is_cancelled() is False


def test_conversation_memory_limit_and_reload(tmp_path):
    path = tmp_path / "conversation_history.json"
    cm = ConversationMemory(path=path, limit=3)
    cm.append({"role": "user", "text": "one"})
    cm.append({"role": "assistant", "text": "two"})
    cm.append({"role": "user", "text": "three"})
    cm.append({"role": "assistant", "text": "four"})

    rows = cm.load(limit=10)
    assert len(rows) == 3
    assert rows[0]["text"] == "two"
    assert rows[-1]["text"] == "four"

    cm2 = ConversationMemory(path=path, limit=3)
    rows2 = cm2.load(limit=10)
    assert rows2[-1]["text"] == "four"


def test_conversation_memory_isolated_by_session(tmp_path):
    path = tmp_path / "conversation_history.json"
    cm = ConversationMemory(path=path, limit=2)
    cm.append({"role": "user", "text": "owner-a1"}, session_id="owner_a")
    cm.append({"role": "assistant", "text": "owner-a2"}, session_id="owner_a")
    cm.append({"role": "user", "text": "owner-b1"}, session_id="owner_b")
    cm.append({"role": "assistant", "text": "owner-b2"}, session_id="owner_b")

    rows_a = cm.load(limit=10, session_id="owner_a")
    rows_b = cm.load(limit=10, session_id="owner_b")

    assert [r["text"] for r in rows_a] == ["owner-a1", "owner-a2"]
    assert [r["text"] for r in rows_b] == ["owner-b1", "owner-b2"]


def test_conversation_memory_persists_session_map_format(tmp_path):
    path = tmp_path / "conversation_history.json"
    cm = ConversationMemory(path=path, limit=2)
    cm.append({"role": "user", "text": "owner-a1"}, session_id="owner_a")
    cm.append({"role": "assistant", "text": "owner-b1"}, session_id="owner_b")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] >= 2
    assert "sessions" in payload
    assert payload["sessions"]["owner_a"][0]["text"] == "owner-a1"
    assert payload["sessions"]["owner_b"][0]["text"] == "owner-b1"


def test_conversation_memory_migrates_legacy_json_into_sqlite_backend(tmp_path):
    path = tmp_path / "conversation_history.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "sessions": {
                    "legacy": [
                        {"role": "user", "text": "hello", "session_id": "legacy"},
                        {"role": "assistant", "text": "world", "session_id": "legacy"},
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cm = ConversationMemory(path=path, limit=5)
    rows = cm.load(session_id="legacy", limit=10)
    assert [r["text"] for r in rows] == ["hello", "world"]
    assert path.with_suffix(".json.sqlite3").exists()
