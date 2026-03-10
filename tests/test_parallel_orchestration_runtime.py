import asyncio
from pathlib import Path

import pytest

from modules.parallel_orchestration_runtime import ParallelNode, ParallelOrchestrationRuntime


@pytest.fixture
def runtime(tmp_path: Path) -> ParallelOrchestrationRuntime:
    return ParallelOrchestrationRuntime(sqlite_path=str(tmp_path / "parallel.db"))


@pytest.mark.asyncio
async def test_parallel_runtime_runs_ready_frontier_in_parallel(runtime: ParallelOrchestrationRuntime):
    calls: list[str] = []

    async def _node(name: str, delay: float = 0.0):
        await asyncio.sleep(delay)
        calls.append(name)
        return {"node": name}

    report = await runtime.run(
        "wf_parallel",
        [
            ParallelNode("a", lambda: _node("a", 0.02)),
            ParallelNode("b", lambda: _node("b", 0.02)),
            ParallelNode("c", lambda: _node("c"), deps=["a", "b"]),
        ],
        run_id="wf_parallel_run",
    )

    assert report["state"] == "completed"
    assert report["completed_count"] == 3
    assert calls[-1] == "c"
    statuses = {row["node_name"]: row["status"] for row in runtime.list_nodes("wf_parallel_run")}
    assert statuses == {"a": "completed", "b": "completed", "c": "completed"}


@pytest.mark.asyncio
async def test_parallel_runtime_blocks_downstream_on_dependency_failure(runtime: ParallelOrchestrationRuntime):
    async def _ok():
        return {"ok": True}

    async def _bad():
        raise RuntimeError("boom")

    report = await runtime.run(
        "wf_failure",
        [
            ParallelNode("ok", _ok),
            ParallelNode("bad", _bad),
            ParallelNode("downstream", _ok, deps=["bad"]),
        ],
        run_id="wf_failure_run",
    )

    assert report["state"] == "degraded"
    nodes = {row["node_name"]: row for row in runtime.list_nodes("wf_failure_run")}
    assert nodes["ok"]["status"] == "completed"
    assert nodes["bad"]["status"] == "failed"
    assert nodes["downstream"]["status"] == "blocked"
