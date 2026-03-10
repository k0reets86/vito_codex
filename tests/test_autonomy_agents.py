import json

import pytest

import modules.owner_model as owner_model_module
import modules.reflector as reflector_module
import modules.skill_library as skill_library_module
from agents.curriculum_agent import CurriculumAgent
from agents.opportunity_scout import OpportunityScout
from agents.self_evolver import SelfEvolver
from goal_engine import GoalEngine, GoalPriority


class _Result:
    def __init__(self, success=True, output=""):
        self.success = success
        self.output = output


@pytest.fixture
def autonomy_env(tmp_path):
    db = tmp_path / "test.sqlite"
    owner_model_module.OWNER_MODEL_FILE = tmp_path / "owner_model.json"
    reflector_module.LEARNINGS_DIR = tmp_path / ".learnings"
    reflector_module.LEARNINGS_FILE = reflector_module.LEARNINGS_DIR / "LEARNINGS.md"
    reflector_module.ATTRIBUTION_FILE = reflector_module.LEARNINGS_DIR / "attribution_map.json"
    skill_library_module.SKILL_LIBRARY_DIR = tmp_path / "skills"
    return db


@pytest.mark.asyncio
async def test_curriculum_agent_generates_filtered_goals(autonomy_env):
    ge = GoalEngine(sqlite_path=str(autonomy_env))
    ge.create_goal("Existing Goal", "desc", priority=GoalPriority.MEDIUM, source="test")
    agent = CurriculumAgent(goal_engine=ge)
    out = await agent.generate_goals()
    assert out["goals"]
    assert len(out["goals"]) <= 3
    assert out["state"]["active_goals"] >= 1


@pytest.mark.asyncio
async def test_opportunity_scout_aggregates_inputs(autonomy_env):
    class Scout(OpportunityScout):
        async def ask(self, capability: str, **kwargs):
            if capability == "trend_scan":
                return _Result(True, "meme trend creator economy")
            if capability == "research":
                return _Result(True, "digital product trends and meme monetization")
            return None

    agent = Scout()
    out = await agent.scan_and_propose()
    assert out["proposals"]
    assert any("meme" in json.dumps(p).lower() for p in out["proposals"])


@pytest.mark.asyncio
async def test_self_evolver_builds_proposals(autonomy_env):
    agent = SelfEvolver(comms=None)
    out = await agent.weekly_improve_cycle()
    assert out["proposals"]
    assert len(out["proposals"]) >= 2
