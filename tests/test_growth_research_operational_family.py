import pytest

from agents.content_creator import ContentCreator
from agents.document_agent import DocumentAgent
from agents.email_agent import EmailAgent
from agents.marketing_agent import MarketingAgent
from agents.research_agent import ResearchAgent
from agents.trend_scout import TrendScout


def _assert_pack(pack: dict):
    assert isinstance(pack, dict)
    assert pack.get("used_skills")
    assert isinstance(pack.get("evidence"), dict)
    assert pack.get("next_actions")
    assert pack.get("recovery_hints")


@pytest.mark.asyncio
async def test_content_creator_turnkey_local_has_operational_pack():
    agent = ContentCreator(llm_router=None, memory=None, finance=None, comms=None)
    result = await agent.execute_task("product_turnkey", topic="AI Swipe Kit", platform="gumroad", price=9)
    assert result.success is True
    assert isinstance(result.output, dict)
    _assert_pack(result.metadata.get("operational_pack"))
    assert result.output.get("used_skills")
    assert isinstance(result.output.get("evidence"), dict)


@pytest.mark.asyncio
async def test_marketing_strategy_local_has_operational_pack():
    agent = MarketingAgent(llm_router=None, memory=None, finance=None, comms=None)
    result = await agent.execute_task("marketing_strategy", product="AI Kit", target_audience="creators", budget_usd=120)
    assert result.success is True
    assert isinstance(result.output, dict)
    _assert_pack(result.metadata.get("operational_pack"))
    assert result.output.get("used_skills")
    assert result.output.get("quality_checks")


@pytest.mark.asyncio
async def test_trend_scout_local_niches_has_operational_pack():
    agent = TrendScout(llm_router=None, memory=None, finance=None, comms=None)
    result = await agent.execute_task("niche_research")
    assert result.success is True
    assert isinstance(result.output, dict)
    _assert_pack(result.metadata.get("operational_pack"))
    assert result.output.get("used_skills")
    assert isinstance(result.output.get("evidence"), dict)


@pytest.mark.asyncio
async def test_email_agent_local_newsletter_has_operational_pack():
    agent = EmailAgent(llm_router=None, memory=None, finance=None, comms=None)
    result = await agent.execute_task("newsletter", topic="Weekly launch notes", audience="buyers")
    assert result.success is True
    assert isinstance(result.output, dict)
    _assert_pack(result.metadata.get("operational_pack"))
    assert result.output.get("used_skills")
    assert result.output.get("quality_checks")


@pytest.mark.asyncio
async def test_document_agent_local_doc_has_operational_pack():
    agent = DocumentAgent(llm_router=None, memory=None, finance=None, comms=None)
    result = await agent.execute_task("documentation", title="Ops runbook", content_type="technical", context={"platform": "etsy"})
    assert result.success is True
    assert isinstance(result.output, dict)
    _assert_pack(result.metadata.get("operational_pack"))
    assert result.output.get("used_skills")
    assert isinstance(result.output.get("evidence"), dict)


@pytest.mark.asyncio
async def test_research_agent_market_analysis_local_has_operational_pack():
    agent = ResearchAgent(llm_router=None, memory=None, finance=None, comms=None)
    result = await agent.execute_task("market_analysis", product_type="digital planners")
    assert result.success is True
    assert isinstance(result.output, dict)
    _assert_pack(result.metadata.get("operational_pack"))
    assert result.output.get("used_skills")
    assert isinstance(result.output.get("evidence"), dict)
