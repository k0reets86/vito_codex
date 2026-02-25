from datetime import timedelta
from unittest.mock import patch

import pytest

from modules.self_learning import SelfLearningEngine


@pytest.fixture
def engine(tmp_path):
    with patch("modules.self_learning.settings") as mock_settings:
        mock_settings.SQLITE_PATH = str(tmp_path / "self_learning.db")
        mock_settings.SELF_LEARNING_SKILL_SCORE_MIN = 0.78
        mock_settings.SELF_LEARNING_MIN_LESSONS = 3
        yield SelfLearningEngine(sqlite_path=str(tmp_path / "self_learning.db"))


def test_threshold_set_and_get(engine):
    assert abs(engine.get_threshold_for_family("research", 0.81) - 0.81) < 1e-6
    engine.set_threshold_for_family("research", 0.9)
    assert abs(engine.get_threshold_for_family("research") - 0.9) < 1e-6
    engine.adjust_threshold_for_family("research", pass_rate=0.9, avg_score=0.8)
    assert engine.get_threshold_for_family("research") < 0.9
    engine.adjust_threshold_for_family("research", pass_rate=0.4, avg_score=0.3)
    assert engine.get_threshold_for_family("research") > 0.7


def test_threshold_clamps(engine):
    engine.set_threshold_for_family("ops", 1.5)
    assert engine.get_threshold_for_family("ops") <= 0.95
    engine.set_threshold_for_family("ops", 0.2)
    assert engine.get_threshold_for_family("ops") >= 0.65
