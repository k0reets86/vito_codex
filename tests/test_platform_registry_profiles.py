import json

from modules import platform_registry as pr


def test_platform_registry_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "PROJECT_ROOT", tmp_path)
    reg = pr.PlatformRegistry(sqlite_path=str(tmp_path / "vito.db"))

    profile = {
        "id": "patreon",
        "name": "Patreon",
        "status": "researching",
        "overview": {"category": "commerce"},
    }
    pid = reg.register_profile(profile)
    assert pid == "patreon"

    reg.update_profile_field("patreon", "integration.method", "api")
    reg.activate_profile("patreon")

    saved = reg.get_profile("patreon")
    assert saved is not None
    assert saved["status"] == "active"
    assert saved["integration"]["method"] == "api"
    assert reg.get_active_platforms(category="commerce")[0]["id"] == "patreon"

    path = tmp_path / "data" / "platform_profiles" / "patreon.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["status"] == "active"

