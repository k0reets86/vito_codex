import json

import pytest

import modules.owner_model as owner_model_module
import modules.reflector as reflector_module
import modules.skill_library as skill_library_module
from modules.autonomy_proposals import AutonomyProposalStore
from decision_loop import DecisionLoop
from goal_engine import GoalEngine, GoalPriority


class _DummyMemory:
    def __init__(self):
        self.knowledge = []
        self.skills = {}
        self.errors = []
        self.episodes = []

    def search_knowledge(self, *_args, **_kwargs):
        return []

    def search_skills(self, *_args, **_kwargs):
        return []

    def store_knowledge(self, **kwargs):
        self.knowledge.append(kwargs)

    def save_skill(self, name, description, **kwargs):
        self.skills[name] = {"description": description, **kwargs}

    def update_skill_last_result(self, name, result):
        self.skills.setdefault(name, {})["last_result"] = result

    def get_skill(self, name):
        return self.skills.get(name)

    def update_skill_success(self, name, success=False):
        self.skills.setdefault(name, {})["success"] = success

    def log_error(self, **kwargs):
        self.errors.append(kwargs)

    async def store_episode(self, **kwargs):
        self.episodes.append(kwargs)


@pytest.mark.asyncio
async def test_decision_loop_learn_from_goal_writes_reflection_and_skill_library(tmp_path):
    db = tmp_path / "test.sqlite"
    owner_model_module.OWNER_MODEL_FILE = tmp_path / "owner_model.json"
    reflector_module.LEARNINGS_DIR = tmp_path / ".learnings"
    reflector_module.LEARNINGS_FILE = reflector_module.LEARNINGS_DIR / "LEARNINGS.md"
    reflector_module.ATTRIBUTION_FILE = reflector_module.LEARNINGS_DIR / "attribution_map.json"
    skill_library_module.SKILL_LIBRARY_DIR = tmp_path / "skills"

    ge = GoalEngine(sqlite_path=str(db))
    memory = _DummyMemory()
    loop = DecisionLoop(goal_engine=ge, llm_router=None, memory=memory, agent_registry=None)

    goal = ge.create_goal(
        title="Create Gumroad listing",
        description="Create full Gumroad listing with file and cover",
        priority=GoalPriority.MEDIUM,
        source="curriculum_agent",
    )
    goal.plan = ["Create Gumroad listing", "Upload file", "Verify public page"]
    results = {
        "all_completed": True,
        "steps_completed": 3,
        "steps_total": 3,
        "duration_ms": 1234,
        "step_1": {"agent": "ecommerce_agent"},
        "step_2": {"agent": "browser_agent"},
        "step_3": {"agent": "quality_judge"},
    }

    await loop._learn_from_goal(goal, results)

    amap = json.loads(reflector_module.ATTRIBUTION_FILE.read_text(encoding="utf-8"))
    assert "goal_execution" in amap
    lib = skill_library_module.VITOSkillLibrary(sqlite_path=str(db))
    found = lib.retrieve("gumroad listing verify", n=5)
    assert any(item["name"].startswith("goal_Create Gumroad listing") for item in found)


@pytest.mark.asyncio
async def test_decision_loop_autonomy_writes_proposal_store(tmp_path):
    db = tmp_path / "test.sqlite"
    owner_model_module.OWNER_MODEL_FILE = tmp_path / "owner_model.json"
    reflector_module.LEARNINGS_DIR = tmp_path / ".learnings"
    reflector_module.LEARNINGS_FILE = reflector_module.LEARNINGS_DIR / "LEARNINGS.md"
    reflector_module.ATTRIBUTION_FILE = reflector_module.LEARNINGS_DIR / "attribution_map.json"
    skill_library_module.SKILL_LIBRARY_DIR = tmp_path / "skills"

    class _Registry:
        async def dispatch(self, task_type, **kwargs):
            class _R:
                success = True
                output = {
                    "proposals": [
                        {"title": "Scout item", "rationale": "why", "expected_revenue": 100, "confidence": 0.8}
                    ],
                    "goals": [
                        {"title": "Curriculum goal", "rationale": "why", "expected_revenue": 90, "confidence": 0.7}
                    ],
                }
            return _R()

    ge = GoalEngine(sqlite_path=str(db))
    memory = _DummyMemory()
    loop = DecisionLoop(goal_engine=ge, llm_router=None, memory=memory, agent_registry=_Registry())
    loop._tick_count = 100

    await loop._maybe_run_opportunity_scout()
    await loop._maybe_run_curriculum_review()

    store = AutonomyProposalStore(sqlite_path=str(db))
    recent = store.list_recent(limit=10)
    titles = {str(item.get("title") or "") for item in recent}
    assert "Scout item" in titles
    assert "Curriculum goal" in titles
