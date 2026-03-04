import pytest

from scripts.mega_agent_audit import run_megatest


@pytest.mark.asyncio
async def test_agent_megatest_combat_readiness():
    report = await run_megatest()
    assert report["total_agents"] >= 23
    assert report["combat_ready_agents"] == report["total_agents"]
    for row in report["rows"]:
        assert row["static"]["score10"] >= 6
        assert row["capabilities"]
        assert any(r["non_wrapper_path"] for r in row["runtime"])

