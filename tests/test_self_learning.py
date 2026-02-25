from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.self_learning import SelfLearningEngine


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
