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


def test_threshold_adjusts_from_promotion_outcomes(engine):
    engine.set_threshold_for_family("research", 0.8)
    conn = engine._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_candidates (skill_name, confidence, task_family, status, updated_at)
            VALUES ('selflearn:outcome_ok', 0.9, 'research', 'promoted', datetime('now'))
            """
        )
        conn.execute(
            """
            INSERT INTO self_learning_promotion_events (skill_name, decision, reason, created_at)
            VALUES ('selflearn:outcome_ok', 'promoted', 'good_outcome', datetime('now'))
            """
        )
        conn.commit()
    finally:
        conn.close()
    before = engine.get_threshold_for_family("research")
    engine.adjust_threshold_for_family("research", pass_rate=0.7, avg_score=0.6)
    after = engine.get_threshold_for_family("research")
    assert after < before


def test_decayed_flaky_rate_prefers_recent_stable_runs(engine):
    conn = engine._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, flaky, attempts, updated_at)
            VALUES
              ('selflearn:decay_skill', 'research', 'old_flaky', 'passed', 1, 2, datetime('now', '-90 day')),
              ('selflearn:decay_skill', 'research', 'recent_ok_1', 'passed', 0, 1, datetime('now')),
              ('selflearn:decay_skill', 'research', 'recent_ok_2', 'passed', 0, 1, datetime('now'))
            """
        )
        conn.commit()
        rate, weighted_runs = engine._decayed_flaky_rate(
            conn=conn,
            skill_name="selflearn:decay_skill",
            window_days=120,
            decay_days=7,
            min_weight=0.05,
        )
    finally:
        conn.close()
    assert weighted_runs > 2.0
    assert rate < 0.2


def test_recalibrate_thresholds_and_list_thresholds(engine):
    conn = engine._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_lessons (goal_id, step_text, status, score, lesson, task_family, created_at)
            VALUES
              ('g1', 'research', 'completed', 0.9, 'ok', 'research', datetime('now')),
              ('g2', 'research', 'completed', 0.8, 'ok', 'research', datetime('now')),
              ('g3', 'research', 'failed', 0.2, 'bad', 'research', datetime('now')),
              ('g4', 'research', 'completed', 0.85, 'ok', 'research', datetime('now'))
            """
        )
        conn.commit()
    finally:
        conn.close()
    out = engine.recalibrate_thresholds(days=30, min_lessons=3)
    assert out["ok"] is True
    rows = engine.list_thresholds(limit=10)
    assert rows
    assert rows[0]["task_family"] == "research"


def test_cleanup_old_test_jobs(engine):
    conn = engine._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, flaky, attempts, updated_at)
            VALUES
              ('selflearn:cleanup', 'research', 'old_passed', 'passed', 0, 1, datetime('now', '-120 day')),
              ('selflearn:cleanup', 'research', 'new_passed', 'passed', 0, 1, datetime('now'))
            """
        )
        conn.commit()
    finally:
        conn.close()
    out = engine.cleanup_old_test_jobs(max_age_days=90)
    assert out["ok"] is True
    assert out["deleted"] >= 1


def test_sync_promotion_outcomes_from_tests_records_postcheck_and_affects_threshold(engine):
    engine.set_threshold_for_family("research", 0.8)
    conn = engine._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_candidates (skill_name, confidence, task_family, status, updated_at)
            VALUES ('selflearn:postcheck_skill', 0.92, 'research', 'promoted', datetime('now'))
            """
        )
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, flaky, attempts, updated_at)
            VALUES
              ('selflearn:postcheck_skill', 'research', 'run1', 'failed', 1, 2, datetime('now')),
              ('selflearn:postcheck_skill', 'research', 'run2', 'passed', 1, 2, datetime('now')),
              ('selflearn:postcheck_skill', 'research', 'run3', 'passed', 0, 1, datetime('now'))
            """
        )
        conn.commit()
    finally:
        conn.close()

    sync = engine.sync_promotion_outcomes_from_tests(days=30, min_runs=2, fail_rate_max=0.2, flaky_rate_max=0.3)
    assert sync["ok"] is True
    assert sync["inserted"] >= 1
    assert sync["failed"] >= 1

    # Same snapshot should not duplicate identical postcheck events.
    sync2 = engine.sync_promotion_outcomes_from_tests(days=30, min_runs=2, fail_rate_max=0.2, flaky_rate_max=0.3)
    assert sync2["inserted"] == 0

    before = engine.get_threshold_for_family("research")
    engine.adjust_threshold_for_family("research", pass_rate=0.7, avg_score=0.6)
    after = engine.get_threshold_for_family("research")
    assert after > before
