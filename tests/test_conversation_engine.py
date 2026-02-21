"""Тесты для ConversationEngine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from conversation_engine import ConversationEngine, Intent, Turn, MAX_CONTEXT_TURNS


@pytest.fixture
def engine(mock_llm_router, mock_memory):
    return ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)


class TestIntentDetection:
    def test_command_intent(self, engine):
        assert engine._detect_intent_rules("/status") == Intent.COMMAND
        assert engine._detect_intent_rules("/goals") == Intent.COMMAND

    def test_approval_intent(self, engine):
        assert engine._detect_intent_rules("да") == Intent.APPROVAL
        assert engine._detect_intent_rules("нет") == Intent.APPROVAL
        assert engine._detect_intent_rules("ok") == Intent.APPROVAL
        assert engine._detect_intent_rules("approve") == Intent.APPROVAL

    def test_no_rule_match(self, engine):
        assert engine._detect_intent_rules("Привет, как дела?") is None
        assert engine._detect_intent_rules("Сделай отчёт") is None

    @pytest.mark.asyncio
    async def test_llm_intent_question(self, engine):
        engine.llm_router.call_llm = AsyncMock(return_value="QUESTION")
        intent = await engine._detect_intent_llm("Сколько мы заработали?")
        assert intent == Intent.QUESTION

    @pytest.mark.asyncio
    async def test_llm_intent_goal_request(self, engine):
        engine.llm_router.call_llm = AsyncMock(return_value="GOAL_REQUEST")
        intent = await engine._detect_intent_llm("Создай шаблоны для Etsy")
        assert intent == Intent.GOAL_REQUEST

    @pytest.mark.asyncio
    async def test_llm_intent_feedback(self, engine):
        engine.llm_router.call_llm = AsyncMock(return_value="FEEDBACK")
        intent = await engine._detect_intent_llm("Отлично сработал!")
        assert intent == Intent.FEEDBACK

    @pytest.mark.asyncio
    async def test_llm_intent_conversation(self, engine):
        engine.llm_router.call_llm = AsyncMock(return_value="CONVERSATION")
        intent = await engine._detect_intent_llm("Привет!")
        assert intent == Intent.CONVERSATION

    @pytest.mark.asyncio
    async def test_llm_intent_fallback(self, engine):
        engine.llm_router.call_llm = AsyncMock(return_value=None)
        intent = await engine._detect_intent_llm("random text")
        assert intent == Intent.CONVERSATION


class TestProcessMessage:
    @pytest.mark.asyncio
    async def test_command_passes_through(self, engine):
        result = await engine.process_message("/status")
        assert result["intent"] == "command"
        assert result["pass_through"] is True

    @pytest.mark.asyncio
    async def test_approval_passes_through(self, engine):
        result = await engine.process_message("да")
        assert result["intent"] == "approval"
        assert result["pass_through"] is True

    @pytest.mark.asyncio
    async def test_question_returns_response(self, engine):
        engine.llm_router.call_llm = AsyncMock(side_effect=[
            "QUESTION",  # Intent detection
            "Мы заработали $50 за неделю",  # Answer
        ])
        result = await engine.process_message("Сколько мы заработали?")
        assert result["intent"] == "question"
        assert result["response"] is not None

    @pytest.mark.asyncio
    async def test_goal_request_creates_goal(self, engine):
        engine.llm_router.call_llm = AsyncMock(side_effect=[
            "GOAL_REQUEST",
            '{"goal_title": "Создать шаблоны Etsy", "confirmation": "Принял! Создаю цель."}',
        ])
        result = await engine.process_message("Создай шаблоны для Etsy")
        assert result["intent"] == "goal_request"
        assert result["create_goal"] is True
        assert "goal_title" in result

    @pytest.mark.asyncio
    async def test_feedback_saves_pattern(self, engine):
        engine.llm_router.call_llm = AsyncMock(side_effect=[
            "FEEDBACK",
            "Спасибо! Учту в следующий раз.",
        ])
        result = await engine.process_message("Отличная работа!")
        assert result["intent"] == "feedback"
        engine.memory.save_pattern.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversation_response(self, engine):
        engine.llm_router.call_llm = AsyncMock(side_effect=[
            "CONVERSATION",
            "Привет! Я VITO, рад помочь.",
        ])
        result = await engine.process_message("Привет!")
        assert result["intent"] == "conversation"
        assert result["response"] is not None


class TestContext:
    def test_add_turn(self, engine):
        engine._add_turn("user", "hello")
        assert len(engine._context) == 1
        assert engine._context[0].role == "user"
        assert engine._context[0].text == "hello"

    def test_context_limit(self, engine):
        for i in range(MAX_CONTEXT_TURNS + 5):
            engine._add_turn("user", f"message {i}")
        assert len(engine._context) == MAX_CONTEXT_TURNS

    def test_format_context_empty(self, engine):
        assert engine._format_context() == "(начало разговора)"

    def test_format_context_with_turns(self, engine):
        engine._add_turn("user", "Привет")
        engine._add_turn("assistant", "Здравствуй!")
        formatted = engine._format_context()
        assert "Владелец: Привет" in formatted
        assert "VITO: Здравствуй!" in formatted

    def test_get_context(self, engine):
        engine._add_turn("user", "test", Intent.QUESTION)
        ctx = engine.get_context()
        assert len(ctx) == 1
        assert ctx[0]["role"] == "user"
        assert ctx[0]["intent"] == "question"

    def test_clear_context(self, engine):
        engine._add_turn("user", "test")
        engine.clear_context()
        assert len(engine._context) == 0
