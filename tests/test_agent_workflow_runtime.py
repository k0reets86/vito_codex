import pytest

from agents.agent_registry import AgentRegistry
from agents.base_agent import BaseAgent, TaskResult
from modules.agent_workflow_runtime import AgentWorkflowRuntime


class GenericAgent(BaseAgent):
    def __init__(self, name, caps, **kwargs):
        super().__init__(name=name, description=name, **kwargs)
        self._caps = caps

    @property
    def capabilities(self):
        return self._caps

    async def execute_task(self, task_type: str, **kwargs):
        return TaskResult(success=True, output={"handled_by": self.name, "task_type": task_type})


class EcommerceWorkflowAgent(GenericAgent):
    async def execute_task(self, task_type: str, **kwargs):
        if task_type == "listing_create":
            return TaskResult(
                success=True,
                output={
                    "status": "draft",
                    "platform": "gumroad",
                    "id": "wf_demo_1",
                    "url": "https://example.test/listing/wf_demo_1",
                    "evidence": {"id": "wf_demo_1", "url": "https://example.test/listing/wf_demo_1"},
                },
            )
        return await super().execute_task(task_type, **kwargs)


def _reg(*agents):
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg


@pytest.mark.asyncio
async def test_w01_runtime_produces_handoff_events():
    reg = _reg(
        GenericAgent("trend_scout", ["trend_scan"]),
        GenericAgent("research_agent", ["research"]),
        GenericAgent("economics_agent", ["pricing_strategy"]),
        GenericAgent("legal_agent", ["legal"]),
        GenericAgent("content_creator", ["content_creation"]),
        GenericAgent("quality_judge", ["quality_review"]),
        GenericAgent("seo_agent", ["listing_seo_pack"]),
        GenericAgent("translation_agent", ["translate"]),
        EcommerceWorkflowAgent("ecommerce_agent", ["listing_create"]),
        GenericAgent("smm_agent", ["campaign_plan"]),
        GenericAgent("analytics_agent", ["analytics"]),
    )
    runtime = AgentWorkflowRuntime(reg)
    out = await runtime.run("W01_digital_product_sales")
    assert len(out["steps"]) == 11
    assert out["steps"][0]["capability"] == "trend_scan"
    assert out["steps"][-1]["capability"] == "analytics"
    assert any(step["success"] for step in out["steps"])
    events = out["events"]
    assert any(e["event"] == "dispatch_start" for e in events)
    assert any(e["event"] == "dispatch_complete" for e in events)


@pytest.mark.asyncio
async def test_w03_runtime_runs_monitor_heal_chain():
    reg = _reg(
        GenericAgent("devops_agent", ["monitoring"]),
        GenericAgent("analytics_agent", ["analytics"]),
        GenericAgent("self_healer", ["self_heal"]),
        GenericAgent("security_agent", ["security"]),
    )
    runtime = AgentWorkflowRuntime(reg)
    out = await runtime.run("W03_monitoring_self_heal")
    assert out["success"] is True
    caps = [s["capability"] for s in out["steps"]]
    assert caps == ["monitoring", "analytics", "self_heal", "security", "monitoring"]


@pytest.mark.asyncio
async def test_unknown_workflow_is_rejected():
    reg = AgentRegistry()
    runtime = AgentWorkflowRuntime(reg)
    out = await runtime.run("W99_unknown")
    assert out["success"] is False
    assert out["error"] == "workflow_not_found"
