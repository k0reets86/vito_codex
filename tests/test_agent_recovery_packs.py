from agents.base_agent import BaseAgent
from modules.agent_recovery_packs import get_agent_recovery_pack


class DummyAgent(BaseAgent):
    @property
    def capabilities(self):
        return ["demo"]

    async def execute_task(self, task_type: str, **kwargs):
        raise NotImplementedError


def test_recovery_packs_exist_for_priority_agents():
    for agent in ("browser_agent", "translation_agent", "economics_agent", "account_manager", "legal_agent"):
        pack = get_agent_recovery_pack(agent)
        assert pack
        assert pack["failure_signatures"]
        assert pack["preferred_actions"]


def test_runtime_profile_includes_recovery_pack():
    agent = DummyAgent(name="browser_agent", description="demo")
    profile = agent.build_runtime_profile("browse")
    assert "recovery" in profile
    assert "failure_signatures" in profile["recovery"]
