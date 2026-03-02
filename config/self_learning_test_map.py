"""Versioned default mapping of self-learning task families to pytest targets."""

from __future__ import annotations

import re


TEST_MAP_VERSION = "2026.03.02.v3"

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
    "recovery": "tests/test_self_learning.py tests/test_self_learning_test_runner.py tests/test_skill_registry.py",
}

FAMILY_ALIASES: dict[str, str] = {
    "security_ops": "security",
    "secops": "security",
    "orchestration": "orchestrate",
    "workflow": "orchestrate",
    "workflow_ops": "orchestrate",
    "publishing": "publish",
    "marketing": "publish",
    "commerce": "publish",
    "revenue": "publish",
    "development": "code",
    "coding": "code",
    "incident_response": "recovery",
    "recovery_ops": "recovery",
    "stability": "recovery",
}


def _normalize_family(task_family: str) -> str:
    raw = re.sub(r"[^a-z0-9_]+", "_", str(task_family or "").strip().lower())
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw:
        return ""
    if raw in DEFAULT_SELF_LEARNING_TEST_MAP:
        return raw
    alias = FAMILY_ALIASES.get(raw, "")
    if alias:
        return alias
    head = raw.split("_", 1)[0]
    if head in DEFAULT_SELF_LEARNING_TEST_MAP:
        return head
    alias = FAMILY_ALIASES.get(head, "")
    if alias:
        return alias
    return raw


def resolve_family_targets(task_family: str, override: str = "") -> str:
    fam = str(task_family or "").strip().lower()
    normalized = _normalize_family(fam)
    candidates = [x for x in [fam, normalized] if x]
    raw = str(override or "").strip()
    if raw:
        for chunk in raw.split(";"):
            part = chunk.strip()
            if not part or "=" not in part:
                continue
            key, val = part.split("=", 1)
            k = _normalize_family(key.strip().lower())
            if val.strip() and k in candidates:
                return val.strip()
    for fam_key in candidates:
        mapped = DEFAULT_SELF_LEARNING_TEST_MAP.get(fam_key, "")
        if mapped:
            return mapped
    return "tests/test_decision_loop.py tests/test_agent_registry.py"
