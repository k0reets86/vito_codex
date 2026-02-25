from unittest.mock import AsyncMock, MagicMock

import pytest

from config.settings import settings
from modules.self_learning import SelfLearningEngine
from modules.skill_registry import SkillRegistry


def test_self_learning_record_and_list(tmp_path):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    sl.record_lesson(goal_id="g1", step_text="research market", status="completed", score=0.9, lesson="works")
    rows = sl.list_lessons(limit=10)
    assert rows
    assert rows[0]["goal_id"] == "g1"


@pytest.mark.asyncio
async def test_self_learning_reflect_creates_candidate(tmp_path):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    llm = MagicMock()
    llm.call_llm = AsyncMock(
        return_value='{"score": 0.91, "lesson": "good reusable flow", "reusable_skill": true, "skill_name": "research_flow", "notes": "stable"}'
    )
    out = await sl.reflect_step(
        llm_router=llm,
        task_type="research",
        goal_id="g2",
        step_text="Research competitors",
        step_result={"status": "completed", "output": "ok"},
        min_skill_score=0.8,
    )
    assert out["score"] >= 0.9
    candidates = sl.list_candidates(limit=10)
    assert candidates
    assert candidates[0]["skill_name"] == "selflearn:research_flow"
    assert candidates[0]["task_family"] == "research"
    lessons = sl.list_lessons(limit=10)
    assert lessons
    assert lessons[0]["task_family"] == "research"


def test_self_learning_optimize_candidates(tmp_path):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    sl.register_candidate("selflearn:seo_flow", confidence=0.6, notes="n")
    for i in range(5):
        sl.record_lesson(
            goal_id=f"g{i}",
            step_text="seo flow step",
            status="completed" if i < 4 else "failed",
            score=0.9 if i < 4 else 0.2,
            lesson="seo flow lesson",
            candidate_skill="selflearn:seo_flow",
        )
    out = sl.optimize_candidates(days=30, min_lessons=3, promote_confidence_min=0.7, auto_promote=False)
    assert out["ok"] is True
    assert out["updated"] >= 1
    rows = sl.list_candidates(limit=10)
    assert rows[0]["optimized_confidence"] >= 0.0
    assert rows[0]["lessons_count"] >= 1


def test_self_learning_auto_promote_ready_with_skill_registry_gates(tmp_path):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:research_flow"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    conn = reg._get_conn()
    try:
        conn.execute(
            "UPDATE skill_registry SET tests_coverage = 0.9, risk_score = 0.1, security_status = 'safe' WHERE name = ?",
            (skill_name,),
        )
        conn.commit()
    finally:
        conn.close()
    sl.register_candidate(skill_name, confidence=0.9, notes="ready")
    sl.set_candidate_status(skill_name, "ready")
    # Add lessons used by promotion safety gate
    for i in range(4):
        sl.record_lesson(
            goal_id=f"g{i}",
            step_text="research flow",
            status="completed",
            score=0.9,
            lesson="works",
            candidate_skill=skill_name,
        )
    sl.optimize_candidates(days=30, min_lessons=3, promote_confidence_min=0.78, auto_promote=False)
    changed = sl.auto_promote_ready_candidates()
    assert changed >= 1
    promoted = sl.list_candidates(limit=10)[0]
    assert promoted["status"] == "promoted"
    row = reg.get_skill(skill_name)
    assert row is not None
    assert row.get("acceptance_status") == "accepted"


def test_self_learning_generate_test_jobs_and_complete(tmp_path):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:test_job_skill"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="needs tests", task_family="research")
    sl.set_candidate_status(skill_name, "ready")
    out = sl.generate_test_jobs(limit=10)
    assert out["ok"] is True
    assert out["created"] >= 1
    jobs = sl.list_test_jobs(status="open", limit=10)
    assert jobs
    assert jobs[0]["skill_name"] == skill_name
    done = sl.complete_test_job(int(jobs[0]["id"]), passed=True, notes="pytest ok")
    assert done is True
    jobs2 = sl.list_test_jobs(status="passed", limit=10)
    assert jobs2
    assert jobs2[0]["attempts"] >= 1


def test_self_learning_summary_has_family_calibration(tmp_path):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    sl.record_lesson("g1", "research step", "completed", 0.9, "ok", task_family="research")
    sl.record_lesson("g2", "research step", "failed", 0.2, "fail", task_family="research")
    summary = sl.summary(days=30)
    assert "family_calibration" in summary
    assert isinstance(summary["family_calibration"], list)


def test_self_learning_auto_promote_blocks_recent_flaky(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_COOLDOWN_HOURS", 72)
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:flaky_skill"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    conn = reg._get_conn()
    try:
        conn.execute(
            "UPDATE skill_registry SET tests_coverage = 0.95, risk_score = 0.1, security_status = 'safe' WHERE name = ?",
            (skill_name,),
        )
        conn.commit()
    finally:
        conn.close()
    sl.register_candidate(skill_name, confidence=0.9, notes="ready", task_family="research")
    sl.set_candidate_status(skill_name, "ready")
    for i in range(4):
        sl.record_lesson(f"g{i}", "research flow", "completed", 0.9, "ok", candidate_skill=skill_name, task_family="research")
    sl.optimize_candidates(days=30, min_lessons=3, promote_confidence_min=0.78, auto_promote=False)
    conn = sl._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, updated_at)
            VALUES (?, ?, 'manual_flaky_seed', 'open', datetime('now'))
            """,
            (skill_name, "research"),
        )
        conn.commit()
    finally:
        conn.close()
    open_jobs = sl.list_test_jobs(status="open", limit=5)
    assert open_jobs
    sl.complete_test_job(int(open_jobs[0]["id"]), passed=True, notes="flaky pass", attempts=2, flaky=True)
    changed = sl.auto_promote_ready_candidates()
    assert changed == 0
    cand = sl.list_candidates(limit=10)[0]
    assert cand["status"] in {"hold", "ready"}
