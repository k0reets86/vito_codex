from modules.service_session_registry import (
    capture_session_snapshot,
    clear_service_session,
    load_service_sessions,
    save_service_sessions,
    update_service_session,
)


def test_service_session_registry_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "sessions.json"
    monkeypatch.setattr("modules.service_session_registry._REGISTRY_PATH", target)
    update_service_session("etsy", verified_at="2026-03-10T00:00:00+00:00")
    rows = load_service_sessions()
    assert "etsy" in rows
    assert rows["etsy"]["verified_at"].startswith("2026-03-10")
    clear_service_session("etsy")
    assert load_service_sessions() == {}


def test_capture_session_snapshot_records_storage(tmp_path, monkeypatch):
    target = tmp_path / "sessions.json"
    storage = tmp_path / "etsy_state.json"
    storage.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("modules.service_session_registry._REGISTRY_PATH", target)
    capture_session_snapshot("etsy", storage_state_path=str(storage), profile_dir="/tmp/profile", verified=True)
    rows = load_service_sessions()
    assert rows["etsy"]["storage_exists"] is True
    assert rows["etsy"]["profile_dir"] == "/tmp/profile"
