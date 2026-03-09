from modules.execution_facts import ExecutionFacts
from modules.failure_memory import FailureMemory
from modules.playbook_registry import PlaybookRegistry
from modules.failure_substrate import build_failure_substrate


def test_build_failure_substrate_merges_failures_facts_and_risky_playbooks(tmp_path):
    db = str(tmp_path / "test.db")
    FailureMemory(sqlite_path=db).record(
        agent="ecommerce_agent",
        task_type="listing_create",
        detail="etsy file upload failed after reload",
        error="missing_file",
    )
    ExecutionFacts(sqlite_path=db).record(
        action="ecommerce_agent:listing_create",
        status="failed",
        detail="publish quality gate failed",
        source="ecommerce_agent",
    )
    reg = PlaybookRegistry(sqlite_path=db)
    reg.learn(
        agent="ecommerce_agent",
        task_type="listing_create",
        action="ecommerce_agent:listing_create",
        status="failed",
        strategy={"detail": "bad path"},
    )
    reg.learn(
        agent="ecommerce_agent",
        task_type="listing_create",
        action="ecommerce_agent:listing_create",
        status="failed",
        strategy={"detail": "bad path 2"},
    )

    out = build_failure_substrate(
        agent="ecommerce_agent",
        task_type="listing_create",
        limit=10,
        sqlite_path=db,
    )

    assert out["agent"] == "ecommerce_agent"
    assert out["task_type"] == "listing_create"
    assert out["signals"]["entry_count"] >= 2
    assert any(x["kind"] == "failure_memory" for x in out["entries"])
    assert any(x["kind"] == "execution_fact" for x in out["entries"])
    assert any(x["kind"] == "risky_playbook" for x in out["entries"])
    assert "ecommerce_agent:listing_create" in out["avoid_actions"]
