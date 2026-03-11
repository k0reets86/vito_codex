from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.conversation_question_lane import handle_question


class DummyIntent:
    QUESTION = SimpleNamespace(value='question')


class DummyLLM:
    async def call_llm(self, **kwargs):
        return 'Ответ из LLM'


class DummyEngine:
    Intent = DummyIntent
    VITO_PERSONALITY = 'VITO'

    def __init__(self):
        self.llm_router = DummyLLM()

    def _normalize_for_nlu(self, text):
        return text.lower()

    def _has_keywords(self, text, kws, fuzzy=False):
        return any(k in text for k in kws)

    def _resolve_owner_name(self):
        return 'Виталий'

    async def _quick_gumroad_analytics(self):
        return 'GMV: $10'

    def _is_time_query(self, lower):
        return 'время' in lower

    def _format_time_answer(self):
        return 'Сейчас 10:00'

    def _quick_answer(self, lower):
        return 'Быстрый ответ' if 'что делаешь' in lower else ''

    def _build_operational_memory_context(self, text, include_errors=True):
        return 'memory ctx'

    def _format_system_context(self):
        return 'system ctx'

    def _format_context(self):
        return 'history'

    def _guard_response(self, response):
        return f'guarded:{response}'


@pytest.mark.asyncio
async def test_question_lane_owner_name_shortcut():
    out = await handle_question(DummyEngine(), 'как меня зовут?')
    assert out['intent'] == 'question'
    assert 'Виталий' in out['response']


@pytest.mark.asyncio
async def test_question_lane_quick_answer_shortcut():
    out = await handle_question(DummyEngine(), 'что делаешь')
    assert out['response'] == 'Быстрый ответ'


@pytest.mark.asyncio
async def test_question_lane_llm_fallback():
    out = await handle_question(DummyEngine(), 'расскажи подробно')
    assert out['response'] == 'guarded:Ответ из LLM'
