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
        responsible_agent="research_agent",
        execution_context={
            "contract": {"agent": "research_agent", "role": "deep_research", "owned_outcomes": ["research_report"]},
            "memory_context": {"playbooks": [{"action": "research_agent:research"}], "recent_failures": [], "recent_facts": []},
        },
    )
    assert out["score"] >= 0.9
    candidates = sl.list_candidates(limit=10)
    assert candidates
    assert candidates[0]["skill_name"] == "selflearn:research_flow"
    assert candidates[0]["task_family"] == "research"
    lessons = sl.list_lessons(limit=10)
    assert lessons
    assert lessons[0]["task_family"] == "research"
    assert lessons[0]["source_agent"] == "research_agent"
    assert candidates[0]["source_agent"] == "research_agent"
    assert candidates[0]["domain_role"] == "deep_research"


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


def test_self_learning_optimize_candidates_uses_agent_signals(tmp_path):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    sl.register_candidate(
        "selflearn:research_flow",
        confidence=0.6,
        notes="n",
        task_family="research",
        source_agent="research_agent",
        domain_role="deep_research",
    )
    for i in range(4):
        sl.record_lesson(
            goal_id=f"g{i}",
            step_text="research flow step",
            status="completed",
            score=0.9,
            lesson="research lesson",
            candidate_skill="selflearn:research_flow",
            task_family="research",
            source_agent="research_agent",
        )
    from modules.playbook_registry import PlaybookRegistry
    PlaybookRegistry(sqlite_path=db).learn(
        agent="research_agent",
        task_type="research",
        action="research_agent:research:good",
        status="success",
        strategy={"detail": "ok"},
    )
    out = sl.optimize_candidates(days=30, min_lessons=3, promote_confidence_min=0.7, auto_promote=False)
    assert out["ok"] is True
    decision = next(x for x in out["decisions"] if x["skill_name"] == "selflearn:research_flow")
    assert decision["source_agent"] == "research_agent"
    assert decision["playbook_signal"] > 0.5


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
    sl.record_lesson("g1", "research step", "completed", 0.9, "ok", task_family="research", source_agent="research_agent")
    sl.record_lesson("g2", "research step", "failed", 0.2, "fail", task_family="research", source_agent="research_agent")
    sl.register_candidate("selflearn:summary_skill", confidence=0.8, notes="ok", task_family="research", source_agent="research_agent")
    summary = sl.summary(days=30)
    assert "family_calibration" in summary
    assert isinstance(summary["family_calibration"], list)
    assert "thresholds" in summary
    assert "source_agents" in summary


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


def test_self_learning_auto_promote_blocks_high_flaky_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_COOLDOWN_HOURS", 0)
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_WINDOW_DAYS", 30)
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_RATE_MAX", 0.3)
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:flaky_rate_skill"
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
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, flaky, attempts, updated_at)
            VALUES (?, 'research', 'seed1', 'passed', 1, 2, datetime('now')),
                   (?, 'research', 'seed2', 'failed', 1, 2, datetime('now')),
                   (?, 'research', 'seed3', 'passed', 0, 1, datetime('now'))
            """,
            (skill_name, skill_name, skill_name),
        )
        conn.commit()
    finally:
        conn.close()
    changed = sl.auto_promote_ready_candidates()
    assert changed == 0
    cand = sl.list_candidates(limit=10)[0]
    assert cand["status"] == "hold"


def test_self_learning_auto_promote_ignores_old_flaky_with_decay(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_COOLDOWN_HOURS", 0)
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_WINDOW_DAYS", 120)
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_RATE_MAX", 0.3)
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_DECAY_DAYS", 7)
    monkeypatch.setattr(settings, "SELF_LEARNING_FLAKY_MIN_WEIGHT", 0.05)
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:stable_after_flake"
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
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, flaky, attempts, updated_at)
            VALUES
              (?, 'research', 'very_old_flaky', 'passed', 1, 2, datetime('now', '-90 day')),
              (?, 'research', 'recent_stable_1', 'passed', 0, 1, datetime('now')),
              (?, 'research', 'recent_stable_2', 'passed', 0, 1, datetime('now'))
            """,
            (skill_name, skill_name, skill_name),
        )
        conn.commit()
    finally:
        conn.close()
    changed = sl.auto_promote_ready_candidates()
    assert changed >= 1
    cand = sl.list_candidates(limit=10)[0]
    assert cand["status"] == "promoted"


def test_self_learning_remediate_degraded_promoted_skills(tmp_path):
    db = str(tmp_path / "sl_remediate.db")
    sl = SelfLearningEngine(sqlite_path=db)
    skill_name = "selflearn:degraded_skill"
    sl.register_candidate(skill_name, confidence=0.93, notes="promoted", task_family="research")
    sl.set_candidate_status(skill_name, "promoted")
    conn = sl._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_promotion_events (skill_name, decision, reason, created_at)
            VALUES (?, 'postcheck_fail', 'postcheck:fail_rate=0.7', datetime('now'))
            """,
            (skill_name,),
        )
        conn.commit()
    finally:
        conn.close()
    out = sl.remediate_degraded_promoted_skills(days=30, max_actions=5)
    assert out["ok"] is True
    assert out["remediated"] == 1
    rows = sl.list_candidates(limit=10)
    assert rows[0]["status"] == "hold"
    jobs = sl.list_test_jobs(status="open", limit=10)
    assert any(j["skill_name"] == skill_name and str(j["reason"]).startswith("postcheck_remediation_") for j in jobs)
    out2 = sl.remediate_degraded_promoted_skills(days=30, max_actions=5)
    assert out2["remediated"] == 0


def test_self_learning_remediation_reason_for_family():
    assert SelfLearningEngine._remediation_reason_for_family("research") == "postcheck_remediation_research"
    assert SelfLearningEngine._remediation_reason_for_family("security/ops") == "postcheck_remediation_security_ops"
    assert SelfLearningEngine._remediation_reason_for_family("") == "postcheck_remediation_generic"


def test_self_learning_remediation_reasons_for_failure_playbooks():
    reasons = SelfLearningEngine._remediation_reasons_for_failure(
        "research",
        "postcheck:fail_rate=0.63;flaky_rate=0.28",
    )
    assert reasons[0] == "postcheck_remediation_research"
    assert "postcheck_remediation_research_regression" in reasons
    assert "postcheck_remediation_research_stability" in reasons
