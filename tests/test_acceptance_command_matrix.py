"""Acceptance tests for owner command matrix (deterministic routes)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from conversation_engine import ConversationEngine


@pytest.mark.asyncio
async def test_acceptance_trend_scan_with_typos_uses_deterministic_route(mock_llm_router, mock_memory):
    registry = MagicMock()
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
    engine._execute_actions = AsyncMock(return_value="[scan_trends][status=completed] trends ready")

    result = await engine.process_message("срчн найди трнды цифрвых продуков для gumroad")
    assert result["intent"] == "system_action"
    assert "[scan_trends][status=completed]" in result["response"]
    engine.llm_router.call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_acceptance_gumroad_stats_with_mixed_language(mock_llm_router, mock_memory):
    registry = MagicMock()
    sales = {"gumroad": {"platform": "gumroad", "sales": 4, "revenue": 77.0, "products_count": 2}}
    registry.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": sales})())
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)

    result = await engine.process_message("pls покажи current статистику на гумроад")
    assert result["intent"] == "question"
    assert "Gumroad (live)" in result["response"]
    assert "Продажи: 4" in result["response"]


@pytest.mark.asyncio
async def test_acceptance_network_check_with_typos(mock_llm_router, mock_memory):
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)

    result = await engine.process_message("проверь достп к интернтту")
    assert result["intent"] == "question"
    assert "Проверка сети" in result["response"]
    assert "общий статус" in result["response"]


@pytest.mark.asyncio
async def test_acceptance_quick_status_and_active_tasks(mock_llm_router, mock_memory):
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)

    result = await engine.process_message("покажи status и активные задачи")
    assert result["intent"] == "question"
    assert "VITO Status (fast)" in result["response"]


@pytest.mark.asyncio
async def test_acceptance_open_url_and_extract_text(mock_llm_router, mock_memory):
    registry = MagicMock()
    registry.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": "page content text"})())
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)

    result = await engine.process_message("открой https://example.com и вытащи текст")
    assert result["intent"] == "question"
    assert "Текст со страницы" in result["response"]
    assert "page content text" in result["response"]


@pytest.mark.asyncio
async def test_acceptance_make_screenshot(mock_llm_router, mock_memory):
    registry = MagicMock()
    registry.dispatch = AsyncMock(
        return_value=type("R", (), {"success": True, "output": {"path": "/tmp/test_screen.png"}})()
    )
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)

    result = await engine.process_message("сделай скрин https://example.com")
    assert result["intent"] == "question"
    assert "Скриншот готов" in result["response"]
    assert "/tmp/test_screen.png" in result["response"]


@pytest.mark.asyncio
async def test_acceptance_change_priority_route(mock_llm_router, mock_memory):
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)
    engine._execute_actions = AsyncMock(return_value="[change_priority][status=completed] done")

    result = await engine.process_message("измени приоритет цели abc123def на high")
    assert result["intent"] == "system_action"
    assert "[change_priority][status=completed]" in result["response"]


@pytest.mark.asyncio
async def test_acceptance_check_system_errors(mock_llm_router, mock_memory):
    healer = MagicMock()
    healer.get_error_stats = MagicMock(return_value={"total": 7, "resolved": 5, "unresolved": 2})
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, self_healer=healer)

    result = await engine.process_message("проверь ошибки системы")
    assert result["intent"] == "question"
    assert "Ошибки системы" in result["response"]
    assert "unresolved: 2" in result["response"]
