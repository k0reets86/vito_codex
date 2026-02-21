"""Тесты для JudgeProtocol."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from judge_protocol import (
    JudgeProtocol,
    JudgeVote,
    JudgeVerdict,
    NicheScore,
    CRITERIA_WEIGHTS,
    NICHE_THRESHOLD,
)


@pytest.fixture
def judge(mock_llm_router, mock_memory, mock_comms):
    return JudgeProtocol(llm_router=mock_llm_router, memory=mock_memory, comms=mock_comms)


class TestNicheScore:
    def test_weighted_score(self):
        score = NicheScore(demand=80, competition=70, margin=90, automation=60, scaling=75)
        expected = (
            80 * 0.30 + 70 * 0.20 + 90 * 0.20 + 60 * 0.15 + 75 * 0.15
        )
        assert score.weighted_score == pytest.approx(expected)

    def test_passes_threshold_true(self):
        score = NicheScore(demand=80, competition=70, margin=80, automation=70, scaling=70)
        assert score.passes_threshold is True

    def test_passes_threshold_false(self):
        score = NicheScore(demand=30, competition=20, margin=30, automation=20, scaling=20)
        assert score.passes_threshold is False

    def test_zero_score(self):
        score = NicheScore()
        assert score.weighted_score == 0.0
        assert score.passes_threshold is False


class TestJudgeVote:
    def test_vote_with_error(self):
        vote = JudgeVote(model="test", score=NicheScore(), error="timeout")
        assert vote.error == "timeout"

    def test_vote_success(self):
        score = NicheScore(demand=75, competition=60, margin=80, automation=70, scaling=65)
        vote = JudgeVote(model="claude-opus", score=score, reasoning="Good niche")
        assert vote.error is None
        assert vote.score.demand == 75


class TestQueryModel:
    @pytest.mark.asyncio
    async def test_query_model_success(self, judge):
        response = json.dumps({
            "demand": 80, "competition": 65, "margin": 75,
            "automation": 70, "scaling": 60, "reasoning": "Good"
        })
        judge.llm_router._call_provider = AsyncMock(return_value=response)

        vote = await judge._query_model("claude-sonnet", "AI templates", None)
        assert vote.error is None
        assert vote.score.demand == 80
        assert vote.reasoning == "Good"

    @pytest.mark.asyncio
    async def test_query_model_invalid_json(self, judge):
        judge.llm_router._call_provider = AsyncMock(return_value="not json")
        vote = await judge._query_model("claude-sonnet", "test niche", None)
        assert vote.error is not None

    @pytest.mark.asyncio
    async def test_query_model_exception(self, judge):
        judge.llm_router._call_provider = AsyncMock(side_effect=Exception("API error"))
        vote = await judge._query_model("claude-sonnet", "test niche", None)
        assert vote.error is not None

    @pytest.mark.asyncio
    async def test_query_model_unknown(self, judge):
        vote = await judge._query_model("unknown_model", "test", None)
        assert vote.error is not None
        assert "not found" in vote.error


class TestEvaluateNiche:
    @pytest.mark.asyncio
    async def test_evaluate_niche_all_models(self, judge):
        response = json.dumps({
            "demand": 80, "competition": 70, "margin": 75,
            "automation": 65, "scaling": 70, "reasoning": "Solid niche"
        })
        judge.llm_router._call_provider = AsyncMock(return_value=response)

        verdict = await judge.evaluate_niche("AI шаблоны для Canva")
        assert isinstance(verdict, JudgeVerdict)
        assert verdict.niche == "AI шаблоны для Canva"
        assert verdict.avg_score > 0
        assert len(verdict.votes) > 0

    @pytest.mark.asyncio
    async def test_evaluate_niche_all_fail(self, judge):
        judge.llm_router._call_provider = AsyncMock(side_effect=Exception("All down"))

        verdict = await judge.evaluate_niche("dead niche")
        assert verdict.avg_score == 0
        assert verdict.approved is False

    @pytest.mark.asyncio
    async def test_evaluate_saves_pattern(self, judge):
        response = json.dumps({
            "demand": 90, "competition": 80, "margin": 85,
            "automation": 75, "scaling": 80, "reasoning": "Excellent"
        })
        judge.llm_router._call_provider = AsyncMock(return_value=response)

        await judge.evaluate_niche("premium niche")
        judge.memory.save_pattern.assert_called()


class TestFormatVerdict:
    def test_format_approved(self, judge):
        verdict = JudgeVerdict(
            niche="AI templates",
            votes=[
                JudgeVote(model="claude-opus", score=NicheScore(80, 70, 75, 60, 65), reasoning="Good"),
            ],
            avg_score=72.5,
            recommendation="AI templates: 72.5/100 — Перспективная ниша.",
            approved=True,
        )
        text = judge.format_verdict_for_telegram(verdict)
        assert "[+]" in text
        assert "ОДОБРЕНА" in text
        assert "72.5" in text

    def test_format_rejected(self, judge):
        verdict = JudgeVerdict(
            niche="Bad niche",
            votes=[],
            avg_score=30.0,
            recommendation="Bad niche: 30.0/100 — Слабая ниша.",
            approved=False,
        )
        text = judge.format_verdict_for_telegram(verdict)
        assert "[-]" in text
        assert "ОТКЛОНЕНА" in text


class TestRecommendation:
    def test_excellent(self, judge):
        rec = judge._generate_recommendation("niche", 85, [])
        assert "Отличная" in rec

    def test_good(self, judge):
        rec = judge._generate_recommendation("niche", 70, [])
        assert "Перспективная" in rec

    def test_medium(self, judge):
        rec = judge._generate_recommendation("niche", 55, [])
        assert "Средняя" in rec

    def test_bad(self, judge):
        rec = judge._generate_recommendation("niche", 30, [])
        assert "Слабая" in rec
