from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.conversation_dialogue_lane import handle_conversation, handle_feedback


class DummyIntent:
    FEEDBACK = SimpleNamespace(value='feedback')
    CONVERSATION = SimpleNamespace(value='conversation')


class DummyLLM:
    async def call_llm(self, **kwargs):
        return 'LLM reply'

    def get_daily_spend(self):
        return 1.25


class DummyMemory:
    def __init__(self):
        self.saved = []

    def save_pattern(self, **kwargs):
        self.saved.append(kwargs)


class DummyEngine:
    Intent = DummyIntent
    VITO_PERSONALITY = 'VITO'

    def __init__(self):
        self.memory = DummyMemory()
        self.llm_router = DummyLLM()

    def _owner_task_focus_text(self):
        return 'owner focus'

    def _format_context(self):
        return 'history'

    def _guard_response(self, response):
        return f'guarded:{response}'


@pytest.mark.asyncio
async def test_feedback_lane_saves_feedback_pattern():
    engine = DummyEngine()
    out = await handle_feedback(engine, 'норм, но покороче')
    assert out['intent'] == 'feedback'
    assert engine.memory.saved
    assert 'LLM reply' in out['response']


@pytest.mark.asyncio
async def test_conversation_lane_uses_guarded_response():
    engine = DummyEngine()
    out = await handle_conversation(engine, 'ну расскажи')
    assert out['intent'] == 'conversation'
    assert out['response'] == 'guarded:LLM reply'
