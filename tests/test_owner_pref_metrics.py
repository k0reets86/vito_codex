from pathlib import Path

from modules.owner_pref_metrics import OwnerPreferenceMetrics
from modules.owner_preference_model import OwnerPreferenceModel
from modules.data_lake import DataLake


def test_owner_pref_metrics_summary(tmp_path: Path):
    db = str(tmp_path / "prefs.db")
    OwnerPreferenceModel(sqlite_path=db).set_preference("tone", "concise")
    DataLake(sqlite_path=db).record(agent="comms", task_type="owner_preference_set", status="success")
    DataLake(sqlite_path=db).record(agent="conversation", task_type="owner_prefs_used", status="success")
    summary = OwnerPreferenceMetrics(sqlite_path=db).summary()
    assert summary["active_prefs"] >= 1
    assert summary["set_events"] >= 1
    assert summary["use_events"] >= 1
