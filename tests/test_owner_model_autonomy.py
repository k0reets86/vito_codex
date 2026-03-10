import modules.owner_model as owner_model_module
from modules.owner_model import OwnerModel


def test_owner_model_updates_from_interaction_and_decision(tmp_path):
    db = tmp_path / "test.sqlite"
    owner_model_module.OWNER_MODEL_FILE = tmp_path / "owner_model.json"
    model = OwnerModel(sqlite_path=str(db))

    model.update_from_interaction("не публикуй, только черновик. на английском")
    prefs = model.get_preferences()
    assert prefs["risk_appetite"] == "low"
    assert prefs["language"] == "en"

    proposal = {
        "title": "Meme Trend Playbook",
        "type": "create",
        "expected_revenue": 150,
        "confidence": 0.81,
    }
    model.update_from_decision(proposal, approved=True)
    prefs2 = model.get_preferences()
    assert "Meme Trend Playbook" in prefs2["approved_patterns"]


def test_owner_model_filters_risky_goals(tmp_path):
    db = tmp_path / "test.sqlite"
    owner_model_module.OWNER_MODEL_FILE = tmp_path / "owner_model.json"
    model = OwnerModel(sqlite_path=str(db))
    goals = [
        {"title": "High risk", "effort": "high", "confidence": 0.6},
        {"title": "Safe medium", "effort": "medium", "confidence": 0.6},
    ]
    filtered = model.filter_goals(goals)
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Safe medium"
