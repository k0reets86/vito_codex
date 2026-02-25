"""Versioned default mapping of self-learning task families to pytest targets."""

from __future__ import annotations

TEST_MAP_VERSION = "2026.02.25.v1"

DEFAULT_SELF_LEARNING_TEST_MAP: dict[str, str] = {
    "research": "tests/test_research_agent.py tests/test_trend_scout.py",
    "strategy": "tests/test_vito_core.py tests/test_decision_loop.py",
    "code": "tests/test_agent_registry.py tests/test_step_contract.py",
    "content": "tests/test_content_creator.py tests/test_seo_agent.py",
    "routine": "tests/test_decision_loop.py tests/test_memory_manager.py",
    "self_learning": "tests/test_self_learning.py tests/test_skill_registry.py",
    "orchestrate": "tests/test_decision_loop.py tests/test_workflow_state_machine.py tests/test_workflow_threads.py",
    "tooling": "tests/test_tooling_runner.py tests/test_tooling_registry.py",
    "security": "tests/test_operator_policy.py tests/test_llm_guardrails.py",
    "publish": "tests/test_platform_scorecard.py tests/test_publisher_queue.py",
}


def resolve_family_targets(task_family: str, override: str = "") -> str:
    fam = str(task_family or "").strip().lower()
    raw = str(override or "").strip()
    if raw:
        for chunk in raw.split(";"):
            part = chunk.strip()
            if not part or "=" not in part:
                continue
            key, val = part.split("=", 1)
            if key.strip().lower() == fam and val.strip():
                return val.strip()
    return DEFAULT_SELF_LEARNING_TEST_MAP.get(fam, "tests/test_decision_loop.py tests/test_agent_registry.py")
