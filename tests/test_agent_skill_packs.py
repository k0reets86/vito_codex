from modules.agent_skill_packs import get_agent_skill_pack


def test_get_agent_skill_pack_returns_runtime_pack():
    pack = get_agent_skill_pack("research_agent")
    assert pack["agent"] == "research_agent"
    assert "iterative_market_research" in pack["skills"]
    assert "overall_score" in pack["evidence"]
