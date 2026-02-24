"""Тесты TrendScout — 6 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestTrendScout:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.trend_scout import TrendScout
        return TrendScout(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "trend_scout"
        assert "trend_scan" in agent.capabilities
        assert "niche_research" in agent.capabilities

    @pytest.mark.asyncio
    async def test_scan_google_trends(self, agent, monkeypatch):
        monkeypatch.setattr("agents.trend_scout.network_available", lambda *args, **kwargs: True)
        class _FakeSeries:
            def __init__(self, vals):
                self._vals = vals
            def tolist(self):
                return self._vals

        class _FakeDF:
            empty = False
            columns = ["AI", "crypto"]
            def __getitem__(self, key):
                return _FakeSeries([10, 12, 15, 18])

        class _FakeRising:
            empty = False
            def head(self, n):
                return self
            def __getitem__(self, key):
                return _FakeSeries(["q1", "q2", "q3"])

        class _FakeTrendReq:
            def __init__(self, *args, **kwargs):
                pass
            def build_payload(self, *args, **kwargs):
                pass
            def interest_over_time(self):
                return _FakeDF()
            def related_queries(self):
                return {"AI": {"rising": _FakeRising()}, "crypto": {"rising": _FakeRising()}}

        import types, sys
        fake_mod = types.SimpleNamespace(TrendReq=_FakeTrendReq)
        sys.modules["pytrends.request"] = fake_mod

        result = await agent.scan_google_trends(["AI", "crypto"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_scan_reddit(self, agent, monkeypatch):
        monkeypatch.setattr("agents.trend_scout.network_available", lambda *args, **kwargs: True)
        agent.llm_router.call_llm = AsyncMock(return_value="Hot topics: side hustle, passive income")
        result = await agent.scan_reddit(["entrepreneur", "passive_income"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_suggest_niches(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="1. Digital planners\n2. AI prompts\n3. Templates")
        result = await agent.suggest_niches()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_trend_scan(self, agent, monkeypatch):
        monkeypatch.setattr("agents.trend_scout.network_available", lambda *args, **kwargs: True)
        class _FakeSeries:
            def __init__(self, vals):
                self._vals = vals
            def tolist(self):
                return self._vals

        class _FakeDF:
            empty = False
            columns = ["AI"]
            def __getitem__(self, key):
                return _FakeSeries([8, 9, 10, 12])

        class _FakeRising:
            empty = False
            def head(self, n):
                return self
            def __getitem__(self, key):
                return _FakeSeries(["q1"])

        class _FakeTrendReq:
            def __init__(self, *args, **kwargs):
                pass
            def build_payload(self, *args, **kwargs):
                pass
            def interest_over_time(self):
                return _FakeDF()
            def related_queries(self):
                return {"AI": {"rising": _FakeRising()}}

        import types, sys
        fake_mod = types.SimpleNamespace(TrendReq=_FakeTrendReq)
        sys.modules["pytrends.request"] = fake_mod

        result = await agent.execute_task("trend_scan", keywords=["AI"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_stores_in_memory(self, agent, monkeypatch):
        monkeypatch.setattr("agents.trend_scout.network_available", lambda *args, **kwargs: True)
        class _FakeSeries:
            def __init__(self, vals):
                self._vals = vals
            def tolist(self):
                return self._vals

        class _FakeDF:
            empty = False
            columns = ["test"]
            def __getitem__(self, key):
                return _FakeSeries([1, 1, 2, 3])

        class _FakeRising:
            empty = False
            def head(self, n):
                return self
            def __getitem__(self, key):
                return _FakeSeries(["q1"])

        class _FakeTrendReq:
            def __init__(self, *args, **kwargs):
                pass
            def build_payload(self, *args, **kwargs):
                pass
            def interest_over_time(self):
                return _FakeDF()
            def related_queries(self):
                return {"test": {"rising": _FakeRising()}}

        import types, sys
        fake_mod = types.SimpleNamespace(TrendReq=_FakeTrendReq)
        sys.modules["pytrends.request"] = fake_mod

        await agent.scan_google_trends(["test"])
        agent.memory.store_knowledge.assert_called()
