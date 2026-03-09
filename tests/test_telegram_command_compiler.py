import json
from unittest.mock import AsyncMock

import pytest

from conversation_engine import ConversationEngine
from modules.owner_task_state import OwnerTaskState
from modules.telegram_command_compiler import (
    compile_owner_message,
    parse_owner_message_structured,
)


@pytest.mark.asyncio
async def test_parse_owner_message_structured_accepts_json_payload(mock_llm_router):
    mock_llm_router.call_llm = AsyncMock(
        return_value=json.dumps(
            {
                "intent": "system_action",
                "task_family": "platform_task",
                "platforms": ["etsy"],
                "topic": "meme playbook",
                "selected_option": 0,
                "target_policy": "new_object",
                "auto_publish": False,
                "needs_confirmation": False,
                "needs_clarification": False,
                "clarification_question": "",
                "short_response": "Запускаю задачу на Etsy.",
                "confidence": 0.93,
            },
            ensure_ascii=False,
        )
    )
    parsed = await parse_owner_message_structured("сдлай на етси", {}, mock_llm_router)
    assert parsed is not None
    assert parsed["intent"] == "system_action"
    assert parsed["platforms"] == ["etsy"]
    assert parsed["confidence"] == pytest.approx(0.93)


@pytest.mark.asyncio
async def test_compile_owner_message_returns_clarification_on_ambiguous_short_command(mock_llm_router):
    mock_llm_router.call_llm = AsyncMock(
        return_value=json.dumps(
            {
                "intent": "system_action",
                "task_family": "generic",
                "platforms": [],
                "topic": "",
                "selected_option": 0,
                "target_policy": "none",
                "auto_publish": False,
                "needs_confirmation": False,
                "needs_clarification": False,
                "clarification_question": "",
                "short_response": "",
                "confidence": 0.52,
            },
            ensure_ascii=False,
        )
    )
    result = await compile_owner_message("делай", {}, mock_llm_router)
    assert result is not None
    assert result["intent"] == "question"
    assert "уточни" in result["response"].lower()


@pytest.mark.asyncio
async def test_compile_owner_message_builds_product_pipeline_from_structured_parse(mock_llm_router):
    active = {"selected_research_title": "Nihilistic Penguin Trend Playbook"}
    mock_llm_router.call_llm = AsyncMock(
        return_value=json.dumps(
            {
                "intent": "system_action",
                "task_family": "product_pipeline",
                "platforms": ["gumroad", "etsy"],
                "topic": "Nihilistic Penguin Trend Playbook",
                "selected_option": 0,
                "target_policy": "new_object",
                "auto_publish": False,
                "needs_confirmation": False,
                "needs_clarification": False,
                "clarification_question": "",
                "short_response": "Собираю продуктовый пайплайн.",
                "confidence": 0.91,
            },
            ensure_ascii=False,
        )
    )
    result = await compile_owner_message("собери новый товар на гумр и этси", active, mock_llm_router)
    assert result is not None
    assert result["intent"] == "system_action"
    assert result["actions"][0]["action"] == "run_product_pipeline"
    assert set(result["actions"][0]["params"]["platforms"]) == {"gumroad", "etsy"}


@pytest.mark.asyncio
async def test_conversation_engine_process_message_uses_structured_clarification(mock_llm_router, mock_memory):
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, owner_task_state=OwnerTaskState())
    engine.owner_task_state.set_active("подготовить новый листинг", source="telegram", intent="goal_request", force=True)
    mock_llm_router.call_llm = AsyncMock(
        return_value=json.dumps(
            {
                "intent": "system_action",
                "task_family": "generic",
                "platforms": [],
                "topic": "",
                "selected_option": 0,
                "target_policy": "none",
                "auto_publish": False,
                "needs_confirmation": False,
                "needs_clarification": True,
                "clarification_question": "Уточни платформу или объект.",
                "short_response": "",
                "confidence": 0.77,
            },
            ensure_ascii=False,
        )
    )
    result = await engine.process_message("делай")
    assert result["intent"] == "question"
    assert "уточни платформу" in result["response"].lower()
