from pathlib import Path

from modules.owner_preference_model import OwnerPreferenceModel


def test_owner_preference_set_get(tmp_path: Path):
    db = str(tmp_path / "prefs.db")
    model = OwnerPreferenceModel(sqlite_path=db)
    model.set_preference(
        key="tone.style",
        value={"tone": "concise", "format": "bullets"},
        source="owner",
        confidence=0.95,
        notes="pref from chat",
    )
    pref = model.get_preference("tone.style")
    assert pref is not None
    assert pref["pref_key"] == "tone.style"
    assert pref["value"]["tone"] == "concise"
    assert float(pref["confidence"]) >= 0.9
    events = model.list_events(pref_key="tone.style", limit=5)
    assert events
    assert events[0]["signal_type"] in {"explicit", "observation", "correction"}


def test_owner_preference_record_signal(tmp_path: Path):
    db = str(tmp_path / "prefs.db")
    model = OwnerPreferenceModel(sqlite_path=db)
    model.record_signal(
        key="approval.threshold",
        value={"usd": 20},
        signal_type="observation",
        source="system",
        confidence_delta=0.2,
    )
    pref = model.get_preference("approval.threshold")
    assert pref is not None
    assert pref["value"]["usd"] == 20
    assert float(pref["confidence"]) >= 0.1


def test_owner_preference_list_and_update_confidence(tmp_path: Path):
    db = str(tmp_path / "prefs.db")
    model = OwnerPreferenceModel(sqlite_path=db)
    model.set_preference(key="timezone", value="UTC", confidence=0.4)
    model.update_confidence("timezone", 0.8)
    prefs = model.list_preferences()
    assert any(p["pref_key"] == "timezone" for p in prefs)
    pref = model.get_preference("timezone")
    assert pref is not None
    assert float(pref["confidence"]) == 0.8


def test_owner_preference_deactivate(tmp_path: Path):
    db = str(tmp_path / "prefs.db")
    model = OwnerPreferenceModel(sqlite_path=db)
    model.set_preference(key="style", value="brief")
    model.deactivate_preference("style", notes="owner request")
    pref = model.get_preference("style")
    assert pref is not None
    assert pref["status"] == "inactive"
