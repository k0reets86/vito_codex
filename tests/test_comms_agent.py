"""Тесты comms_agent.py."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest as TgBadRequest

from agents.base_agent import TaskResult
from comms_agent import CommsAgent
from config.settings import settings
from modules.owner_task_state import OwnerTaskState
from modules.owner_preference_model import OwnerPreferenceModel


@pytest.fixture
def comms():
    """CommsAgent с мок-ботом."""
    agent = CommsAgent()
    # Test isolation: ignore persisted runtime auth/context state.
    agent._service_auth_confirmed = {}
    agent._last_service_context = ""
    agent._last_service_context_at = ""
    agent._bot = AsyncMock()
    agent._bot.send_message = AsyncMock()
    agent._bot.send_document = AsyncMock()
    return agent


@pytest.fixture
def mock_update():
    """Мок Telegram Update от владельца."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = int(CommsAgent()._owner_id)
    update.effective_user = MagicMock()
    update.effective_user.is_bot = False
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = ""
    update.message.reply_to_message = None
    return update


@pytest.fixture
def stranger_update():
    """Мок Telegram Update от чужого пользователя."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 999999999
    update.effective_user = MagicMock()
    update.effective_user.is_bot = False
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


# ── Безопасность ──

def test_is_owner(comms, mock_update):
    assert comms._is_owner(mock_update) is True


def test_is_not_owner(comms, stranger_update):
    assert comms._is_owner(stranger_update) is False


def test_is_owner_no_chat():
    agent = CommsAgent()
    update = MagicMock()
    update.effective_chat = None
    assert agent._is_owner(update) is False


@pytest.mark.asyncio
async def test_reject_stranger(comms, stranger_update):
    result = await comms._reject_stranger(stranger_update)
    assert result is True


@pytest.mark.asyncio
async def test_accept_owner(comms, mock_update):
    result = await comms._reject_stranger(mock_update)
    assert result is False


@pytest.mark.asyncio
async def test_reject_bot_sender_even_in_owner_chat(comms, mock_update):
    mock_update.effective_user.is_bot = True
    result = await comms._reject_stranger(mock_update)
    assert result is True


@pytest.mark.asyncio
async def test_on_attachment_document_routes_document_parse(comms, mock_update, tmp_path):
    async def _download(custom_path: str):
        Path(custom_path).write_text("doc body", encoding="utf-8")

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock(side_effect=_download)
    doc = MagicMock()
    doc.file_name = "sample.txt"
    doc.file_unique_id = "doc123"
    doc.get_file = AsyncMock(return_value=tg_file)

    mock_update.message.document = doc
    mock_update.message.photo = None
    mock_update.message.video = None
    mock_update.message.caption = ""

    comms._agent_registry = MagicMock()
    comms._agent_registry.dispatch = AsyncMock(return_value=TaskResult(success=True, output={"text": "parsed doc"}))
    comms._conversation_engine = MagicMock()
    comms._conversation_engine.process_message = AsyncMock(return_value={"intent": "question"})
    comms._maybe_brainstorm_from_text = AsyncMock(return_value=False)

    await comms._on_attachment(mock_update, MagicMock())

    comms._agent_registry.dispatch.assert_awaited_once()
    args = comms._agent_registry.dispatch.await_args
    assert args.args[0] == "document_parse"
    assert "sample.txt" in str(args.kwargs.get("path", ""))


@pytest.mark.asyncio
async def test_on_attachment_photo_routes_image_ocr(comms, mock_update):
    async def _download(custom_path: str):
        Path(custom_path).write_text("fake image bytes", encoding="utf-8")

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock(side_effect=_download)
    photo = MagicMock()
    photo.file_unique_id = "photo123"
    photo.get_file = AsyncMock(return_value=tg_file)

    mock_update.message.document = None
    mock_update.message.photo = [photo]
    mock_update.message.video = None
    mock_update.message.caption = ""

    comms._agent_registry = MagicMock()
    comms._agent_registry.dispatch = AsyncMock(return_value=TaskResult(success=True, output={"text": "ocr text"}))
    comms._conversation_engine = MagicMock()
    comms._conversation_engine.process_message = AsyncMock(return_value={"intent": "question"})
    comms._maybe_brainstorm_from_text = AsyncMock(return_value=False)

    await comms._on_attachment(mock_update, MagicMock())

    args = comms._agent_registry.dispatch.await_args
    assert args.args[0] == "image_ocr"
    assert "photo_photo123.jpg" in str(args.kwargs.get("path", ""))


@pytest.mark.asyncio
async def test_on_attachment_video_routes_video_extract(comms, mock_update):
    async def _download(custom_path: str):
        Path(custom_path).write_text("fake video bytes", encoding="utf-8")

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock(side_effect=_download)
    video = MagicMock()
    video.file_unique_id = "video123"
    video.get_file = AsyncMock(return_value=tg_file)

    mock_update.message.document = None
    mock_update.message.photo = None
    mock_update.message.video = video
    mock_update.message.caption = ""

    comms._agent_registry = MagicMock()
    comms._agent_registry.dispatch = AsyncMock(return_value=TaskResult(success=True, output={"text": "video text"}))
    comms._conversation_engine = MagicMock()
    comms._conversation_engine.process_message = AsyncMock(return_value={"intent": "question"})
    comms._maybe_brainstorm_from_text = AsyncMock(return_value=False)

    await comms._on_attachment(mock_update, MagicMock())

    args = comms._agent_registry.dispatch.await_args
    assert args.args[0] == "video_extract"
    assert "video_video123.mp4" in str(args.kwargs.get("path", ""))


# ── Команды ──

@pytest.mark.asyncio
async def test_cmd_start(comms, mock_update):
    await comms._cmd_start(mock_update, MagicMock())
    mock_update.message.reply_text.assert_called_once()
    text = mock_update.message.reply_text.call_args[0][0]
    assert "/status" in text
    assert "/goals" in text


@pytest.mark.asyncio
async def test_cmd_start_stranger(comms, stranger_update):
    await comms._cmd_start(stranger_update, MagicMock())
    stranger_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_help_without_topic_uses_inline_sections(comms, mock_update):
    ctx = MagicMock()
    ctx.args = []

    await comms._cmd_help(mock_update, ctx)

    kwargs = mock_update.message.reply_text.call_args[1]
    from telegram import InlineKeyboardMarkup

    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
    rows = kwargs["reply_markup"].inline_keyboard
    labels = [btn.text for row in rows for btn in row]
    assert "Ежедневные" in labels
    assert "Редкие" in labels
    assert "Системные" in labels


@pytest.mark.asyncio
async def test_cmd_status(comms, mock_update):
    dl_mock = MagicMock()
    dl_mock.get_status.return_value = {"running": True, "tick_count": 5, "daily_spend": 1.23}
    ge_mock = MagicMock()
    ge_mock.get_stats.return_value = {"total": 3, "completed": 1, "executing": 1, "pending": 1}
    ge_mock.get_all_goals.return_value = []
    comms.set_modules(goal_engine=ge_mock, decision_loop=dl_mock)

    await comms._cmd_status(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "VITO Status" in text
    assert "работает" in text


@pytest.mark.asyncio
async def test_cmd_status_reload_goals_called(comms, mock_update):
    dl_mock = MagicMock()
    dl_mock.get_status.return_value = {"running": False, "tick_count": 0, "daily_spend": 0.0}
    ge_mock = MagicMock()
    ge_mock.get_all_goals.return_value = []
    comms.set_modules(goal_engine=ge_mock, decision_loop=dl_mock)

    await comms._cmd_status(mock_update, MagicMock())

    ge_mock.reload_goals.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_status_uses_unified_snapshot_with_spend_breakdown(comms, mock_update):
    dl_mock = MagicMock()
    dl_mock.get_status.return_value = {"running": True, "tick_count": 11, "daily_spend": 0.33}
    ge_mock = MagicMock()
    ge_mock.get_all_goals.return_value = []
    llm_mock = MagicMock()
    llm_mock.get_daily_spend.return_value = 1.2
    fin_mock = MagicMock()
    fin_mock.get_daily_spent.return_value = 2.4
    comms.set_modules(goal_engine=ge_mock, decision_loop=dl_mock, llm_router=llm_mock, finance=fin_mock)

    await comms._cmd_status(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Траты сегодня: LLM $1.20; Финконтроль $2.40" in text


@pytest.mark.asyncio
async def test_cmd_goals_empty(comms, mock_update):
    ge_mock = MagicMock()
    ge_mock.get_all_goals.return_value = []
    comms.set_modules(goal_engine=ge_mock)

    await comms._cmd_goals(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Нет целей" in text


@pytest.mark.asyncio
async def test_cmd_goals_no_engine(comms, mock_update):
    comms._goal_engine = None
    await comms._cmd_goals(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "GoalEngine не подключён" in text


@pytest.mark.asyncio
async def test_cmd_spend(comms, mock_update):
    llm_mock = MagicMock()
    llm_mock.get_daily_spend.return_value = 3.45
    comms.set_modules(llm_router=llm_mock)

    await comms._cmd_spend(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "$3.45" in text


@pytest.mark.asyncio
async def test_cmd_goal_create(comms, mock_update, tmp_path):
    from goal_engine import GoalEngine
    ge = GoalEngine()
    owner_task_state = OwnerTaskState(path=tmp_path / "owner_task_state_goal.json")
    comms.set_modules(goal_engine=ge, owner_task_state=owner_task_state)

    mock_update.message.text = "/goal Заработать на Etsy шаблонах"
    await comms._cmd_goal(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Цель создана" in text
    assert len(ge._goals) == 1
    active = owner_task_state.get_active()
    assert active is not None
    assert "etsy" in active.get("text", "").lower()


@pytest.mark.asyncio
async def test_cmd_clear_goals_requires_confirmation(comms, mock_update):
    ge = MagicMock()
    ge.clear_all_goals = MagicMock(return_value=3)
    comms.set_modules(goal_engine=ge)
    ctx = MagicMock()
    ctx.args = []
    await comms._cmd_clear_goals(mock_update, ctx)
    ge.clear_all_goals.assert_not_called()
    text = mock_update.message.reply_text.call_args[0][0]
    assert "/clear_goals yes" in text


@pytest.mark.asyncio
async def test_cmd_clear_goals_with_confirmation(comms, mock_update):
    ge = MagicMock()
    ge.clear_all_goals = MagicMock(return_value=3)
    comms.set_modules(goal_engine=ge)
    ctx = MagicMock()
    ctx.args = ["yes"]
    await comms._cmd_clear_goals(mock_update, ctx)
    ge.clear_all_goals.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_rollback_requires_confirmation(comms, mock_update):
    su = MagicMock()
    su.get_update_history.return_value = [{"backup_path": "/tmp/backup_a"}]
    su.rollback = MagicMock(return_value=True)
    comms.set_modules(self_updater=su)
    ctx = MagicMock()
    ctx.args = []

    await comms._cmd_rollback(mock_update, ctx)

    su.rollback.assert_not_called()
    assert comms._pending_owner_confirmation is not None
    assert comms._pending_owner_confirmation.get("kind") == "rollback"
    text = mock_update.message.reply_text.call_args[0][0]
    assert "/rollback yes" in text


@pytest.mark.asyncio
async def test_cmd_rollback_with_confirmation(comms, mock_update):
    su = MagicMock()
    su.get_update_history.return_value = [{"backup_path": "/tmp/backup_a"}]
    su.rollback = MagicMock(return_value=True)
    comms.set_modules(self_updater=su)
    ctx = MagicMock()
    ctx.args = ["yes"]

    await comms._cmd_rollback(mock_update, ctx)

    su.rollback.assert_called_once_with("/tmp/backup_a")


@pytest.mark.asyncio
async def test_cmd_goal_empty(comms, mock_update):
    ge = MagicMock()
    comms.set_modules(goal_engine=ge)
    mock_update.message.text = "/goal"
    await comms._cmd_goal(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Использование" in text


@pytest.mark.asyncio
async def test_cmd_stop_requires_confirmation(comms, mock_update):
    decision_loop = MagicMock()
    comms.set_modules(decision_loop=decision_loop)
    ctx = MagicMock()
    ctx.args = []
    await comms._cmd_stop(mock_update, ctx)
    decision_loop.stop.assert_not_called()
    text = mock_update.message.reply_text.call_args[0][0]
    assert "/stop yes" in text


@pytest.mark.asyncio
async def test_cmd_stop_with_confirmation(comms, mock_update):
    decision_loop = MagicMock()
    comms.set_modules(decision_loop=decision_loop)
    ctx = MagicMock()
    ctx.args = ["yes"]
    await comms._cmd_stop(mock_update, ctx)
    decision_loop.stop.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_prefs(comms, mock_update, tmp_path: Path):
    old_path = settings.SQLITE_PATH
    try:
        settings.SQLITE_PATH = str(tmp_path / "prefs.db")
        OwnerPreferenceModel().set_preference("tone.style", {"tone": "concise"}, confidence=0.9)
        await comms._cmd_prefs(mock_update, MagicMock())
        text = mock_update.message.reply_text.call_args[0][0]
        assert "Предпочтения владельца" in text
        assert "tone.style" in text
    finally:
        settings.SQLITE_PATH = old_path


@pytest.mark.asyncio
async def test_pref_deactivate_command(comms, tmp_path: Path):
    old_path = settings.SQLITE_PATH
    try:
        settings.SQLITE_PATH = str(tmp_path / "prefs.db")
        OwnerPreferenceModel().set_preference("style", "brief")
        await comms._handle_owner_text("/pref_del style")
        pref = OwnerPreferenceModel().get_preference("style")
        assert pref is not None
        assert pref["status"] == "inactive"
    finally:
        settings.SQLITE_PATH = old_path


@pytest.mark.asyncio
async def test_cmd_prefs_metrics(comms, mock_update, tmp_path: Path):
    old_path = settings.SQLITE_PATH
    try:
        settings.SQLITE_PATH = str(tmp_path / "prefs.db")
        await comms._cmd_prefs_metrics(mock_update, MagicMock())
        text = mock_update.message.reply_text.call_args[0][0]
        assert "Метрики предпочтений" in text
    finally:
        settings.SQLITE_PATH = old_path


@pytest.mark.asyncio
async def test_cmd_packs(comms, mock_update, tmp_path: Path, monkeypatch):
    root = tmp_path / "capability_packs" / "demo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "spec.json").write_text('{"name":"demo","category":"x","acceptance_status":"pending"}', encoding="utf-8")
    monkeypatch.setattr(comms, "_send_packs", lambda reply_to=None: mock_update.message.reply_text("Capability packs:"))
    await comms._cmd_packs(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Capability packs" in text


def test_apply_llm_mode_free_sets_expected_values(comms):
    comms._set_env_values = MagicMock(return_value=True)
    ok, msg = comms._apply_llm_mode("free")
    assert ok is True
    assert "FREE" in msg
    comms._set_env_values.assert_called_once()
    payload = comms._set_env_values.call_args[0][0]
    assert payload["LLM_ROUTER_MODE"] == "free"
    assert payload["LLM_FORCE_GEMINI_FREE"] == "true"
    assert payload["LLM_FORCE_GEMINI_MODEL"] == "gemini-2.5-flash"
    assert payload["LLM_ENABLED_MODELS"] == "gemini-2.5-flash"
    assert payload["IMAGE_ROUTER_PREFER_GEMINI"] == "true"


@pytest.mark.asyncio
async def test_cmd_llm_mode_status(comms, mock_update):
    comms._apply_llm_mode = MagicMock(return_value=(True, "LLM mode status"))
    ctx = MagicMock()
    ctx.args = ["status"]
    await comms._cmd_llm_mode(mock_update, ctx)
    comms._apply_llm_mode.assert_called_once_with("status")
    text = mock_update.message.reply_text.call_args[0][0]
    assert "LLM mode status" in text


# ── Одобрение ──

@pytest.mark.asyncio
async def test_cmd_approve(comms, mock_update):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req_1"] = future

    await comms._cmd_approve(mock_update, MagicMock())
    assert future.result() is True
    assert "req_1" not in comms._pending_approvals


@pytest.mark.asyncio
async def test_cmd_reject(comms, mock_update):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req_2"] = future

    await comms._cmd_reject(mock_update, MagicMock())
    assert future.result() is False
    assert "req_2" not in comms._pending_approvals


@pytest.mark.asyncio
async def test_cmd_approve_empty(comms, mock_update):
    await comms._cmd_approve(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Нет запросов" in text


@pytest.mark.asyncio
async def test_cmd_reject_empty(comms, mock_update):
    await comms._cmd_reject(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Нет запросов" in text


@pytest.mark.asyncio
async def test_cmd_cancel_sets_flag_stops_loop_and_clears_pending(comms, mock_update):
    cancel_state = MagicMock()
    decision_loop = MagicMock()
    pending_future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req_cancel"] = pending_future
    comms._pending_schedule_update = {"choices": [1]}
    comms.set_modules(cancel_state=cancel_state, decision_loop=decision_loop)

    await comms._cmd_cancel(mock_update, MagicMock())

    cancel_state.cancel.assert_called_once()
    decision_loop.stop.assert_called_once()
    assert comms._pending_approvals == {}
    assert comms._pending_schedule_update is None
    text = mock_update.message.reply_text.call_args[0][0]
    assert "приостановлено" in text.lower()


@pytest.mark.asyncio
async def test_cmd_resume_clears_cancel_flag(comms, mock_update):
    cancel_state = MagicMock()
    decision_loop = MagicMock()
    decision_loop.run = AsyncMock()
    decision_loop.running = False
    comms.set_modules(cancel_state=cancel_state, decision_loop=decision_loop)

    await comms._cmd_resume(mock_update, MagicMock())

    cancel_state.clear.assert_called_once()
    text = mock_update.message.reply_text.call_args[0][0]
    assert "возобновл" in text.lower()


@pytest.mark.asyncio
async def test_cmd_cancel_clears_owner_task_state(comms, mock_update, tmp_path):
    from goal_engine import GoalEngine, GoalPriority, GoalStatus
    ge = GoalEngine(sqlite_path=str(tmp_path / "goals_cancel.db"))
    g1 = ge.create_goal("pending goal", "desc", priority=GoalPriority.HIGH)
    g2 = ge.create_goal("waiting goal", "desc", priority=GoalPriority.HIGH)
    ge.wait_for_approval(g2.goal_id, reason="manual")
    owner_task_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_task_state.set_active("сделай отчет", intent="goal_request")
    cancel_state = MagicMock()
    decision_loop = MagicMock()
    decision_loop.orchestrator = MagicMock()
    decision_loop.interrupts = MagicMock()
    comms.set_modules(goal_engine=ge, cancel_state=cancel_state, decision_loop=decision_loop, owner_task_state=owner_task_state)

    await comms._cmd_cancel(mock_update, MagicMock())
    assert owner_task_state.get_active() is None
    assert ge._goals[g1.goal_id].status == GoalStatus.CANCELLED
    assert ge._goals[g2.goal_id].status == GoalStatus.CANCELLED


@pytest.mark.asyncio
async def test_cmd_task_current_and_done(comms, mock_update, tmp_path):
    owner_task_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_task_state.set_active("подготовить публикацию", intent="goal_request")
    comms.set_modules(owner_task_state=owner_task_state)

    await comms._cmd_task_current(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Текущая задача владельца" in text
    await comms._cmd_task_done(mock_update, MagicMock())
    assert owner_task_state.get_active() is None


@pytest.mark.asyncio
async def test_cmd_task_replace(comms, mock_update, tmp_path):
    owner_task_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_task_state.set_active("старая задача", intent="goal_request")
    comms.set_modules(owner_task_state=owner_task_state)
    mock_update.message.text = "/task_replace новая задача"
    await comms._cmd_task_replace(mock_update, MagicMock())
    active = owner_task_state.get_active()
    assert active is not None
    assert "новая задача" in active.get("text", "")


@pytest.mark.asyncio
async def test_cmd_task_cancel(comms, mock_update, tmp_path):
    owner_task_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_task_state.set_active("активная задача", intent="goal_request")
    comms.set_modules(owner_task_state=owner_task_state)
    await comms._cmd_task_cancel(mock_update, MagicMock())
    assert owner_task_state.get_active() is None
    text = mock_update.message.reply_text.call_args[0][0]
    assert "отменена" in text.lower()


@pytest.mark.asyncio
async def test_cmd_status_includes_current_task(comms, mock_update, tmp_path):
    owner_task_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_task_state.set_active("подготовить отчёт", intent="goal_request")
    dl_mock = MagicMock()
    dl_mock.get_status.return_value = {"running": True, "tick_count": 5, "daily_spend": 1.23}
    ge_mock = MagicMock()
    ge_mock.get_stats.return_value = {"total": 3, "completed": 1, "executing": 1, "pending": 1}
    comms.set_modules(goal_engine=ge_mock, decision_loop=dl_mock, owner_task_state=owner_task_state)
    await comms._cmd_status(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Текущая задача" in text


# ── Текстовые сообщения с approval ──

@pytest.mark.asyncio
async def test_on_message_approve_text(comms, mock_update):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req"] = future
    mock_update.message.text = "да"

    await comms._on_message(mock_update, MagicMock())
    assert future.result() is True


@pytest.mark.asyncio
async def test_on_message_reject_text(comms, mock_update):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req"] = future
    mock_update.message.text = "нет"

    await comms._on_message(mock_update, MagicMock())
    assert future.result() is False


@pytest.mark.asyncio
async def test_on_message_owner_confirmation_has_priority_over_pending_approvals(comms, mock_update):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req"] = future
    ge = MagicMock()
    ge.clear_all_goals.return_value = 3
    comms.set_modules(goal_engine=ge)
    comms._pending_owner_confirmation = {"kind": "clear_goals"}
    mock_update.message.text = "да"

    await comms._on_message(mock_update, MagicMock())

    ge.clear_all_goals.assert_called_once()
    assert future.done() is False
    assert comms._pending_owner_confirmation is None


@pytest.mark.asyncio
async def test_on_message_sets_pending_system_action_without_auto_execute(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={
        "intent": "system_action",
        "response": "Подтверди запуск",
        "actions": [{"action": "scan_trends", "params": {}}],
        "needs_confirmation": True,
    })
    conv._execute_actions = AsyncMock(return_value="ok")
    comms.set_modules(conversation_engine=conv)
    mock_update.message.text = "запусти сканирование"

    with patch("comms_agent.settings.AUTONOMY_MAX_MODE", False):
        await comms._on_message(mock_update, MagicMock())

    assert comms._pending_system_action is not None
    conv._execute_actions.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_autonomy_max_auto_executes_confirmation_actions(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(
        return_value={
            "intent": "system_action",
            "response": "Подтверди запуск",
            "actions": [{"action": "scan_trends", "params": {}}],
            "needs_confirmation": True,
        }
    )
    conv._execute_actions = AsyncMock(return_value="[scan_trends] done")
    comms.set_modules(conversation_engine=conv)
    mock_update.message.text = "запусти сканирование"

    with patch("comms_agent.settings.AUTONOMY_MAX_MODE", True):
        await comms._on_message(mock_update, MagicMock())

    conv._execute_actions.assert_called_once()
    assert comms._pending_system_action is None


@pytest.mark.asyncio
async def test_on_message_approves_pending_system_action_and_executes(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"intent": "conversation", "response": "ok"})
    conv._execute_actions = AsyncMock(return_value="[scan_trends] done")
    comms.set_modules(conversation_engine=conv)
    comms._pending_system_action = {"actions": [{"action": "scan_trends", "params": {}}]}
    mock_update.message.text = "да"

    await comms._on_message(mock_update, MagicMock())

    conv._execute_actions.assert_called_once()
    assert comms._pending_system_action is None


@pytest.mark.asyncio
async def test_on_message_numeric_selects_pending_system_action_variant(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"intent": "conversation", "response": "ok"})
    conv._execute_actions = AsyncMock(return_value="[do_b] done")
    comms.set_modules(conversation_engine=conv)
    comms._pending_system_action = {
        "actions": [
            {"action": "do_a", "params": {}},
            {"action": "do_b", "params": {}},
        ]
    }
    mock_update.message.text = "2"
    with patch("comms_agent.settings.TELEGRAM_STRICT_COMMANDS", False):
        await comms._on_message(mock_update, MagicMock())

    conv._execute_actions.assert_called_once()
    args = conv._execute_actions.call_args[0][0]
    assert len(args) == 1
    assert args[0]["action"] == "do_b"
    assert comms._pending_system_action is None


@pytest.mark.asyncio
async def test_on_message_numeric_choice_expands_with_context(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"intent": "conversation", "response": "Принял."})
    comms.set_modules(conversation_engine=conv)
    comms._pending_choice_context = {"saved_at": "now"}
    mock_update.message.text = "5"
    with patch("comms_agent.settings.TELEGRAM_STRICT_COMMANDS", False):
        await comms._on_message(mock_update, MagicMock())

    sent = conv.process_message.call_args[0][0]
    assert "вариант 5" in sent.lower()
    assert comms._pending_choice_context is None


@pytest.mark.asyncio
async def test_on_message_strict_mode_skips_natural_schedule(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"intent": "conversation", "response": "ok"})
    comms.set_modules(conversation_engine=conv)
    comms._maybe_schedule_from_text = AsyncMock(return_value=True)
    mock_update.message.text = "каждый день в 9 отчет по продажам"
    with patch("comms_agent.settings.TELEGRAM_STRICT_COMMANDS", True), patch(
        "comms_agent.settings.AUTONOMY_MAX_MODE", False
    ):
        await comms._on_message(mock_update, MagicMock())
    comms._maybe_schedule_from_text.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_non_strict_mode_allows_natural_schedule(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"intent": "conversation", "response": "ok"})
    comms.set_modules(conversation_engine=conv)
    comms._maybe_schedule_from_text = AsyncMock(return_value=True)
    mock_update.message.text = "каждый день в 9 отчет по продажам"
    with patch("comms_agent.settings.TELEGRAM_STRICT_COMMANDS", False):
        await comms._on_message(mock_update, MagicMock())
    comms._maybe_schedule_from_text.assert_called_once()


@pytest.mark.asyncio
async def test_on_message_regular(comms, mock_update):
    mock_update.message.text = "Сделай мне продукт"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Не понял" in text


@pytest.mark.asyncio
async def test_on_message_kdp_login_shortcut(comms, mock_update):
    mock_update.message.text = "зайди на амазон"
    comms._handle_kdp_login_flow = AsyncMock(return_value=True)
    await comms._on_message(mock_update, MagicMock())
    comms._handle_kdp_login_flow.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_message_kdp_login_real_path_bypasses_conversation(comms, mock_update):
    mock_update.message.text = "зайди на амазон"
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)
    comms._run_kdp_prepare_otp = AsyncMock(return_value=(2, "OTP_REQUIRED: send code now"))

    await comms._on_message(mock_update, MagicMock())

    conv.process_message.assert_not_called()
    sent_texts = [call.args[0] for call in mock_update.message.reply_text.call_args_list]
    assert any(("Amazon KDP" in text or "6-значный код" in text) for text in sent_texts)


@pytest.mark.asyncio
async def test_on_message_reply_context_passed_to_conversation_engine(comms, mock_update):
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"intent": "conversation", "response": "ok"})
    comms.set_modules(conversation_engine=conv)
    parent = MagicMock()
    parent.message_id = 321
    parent.text = "Старое сообщение VITO про план публикации"
    mock_update.message.reply_to_message = parent
    mock_update.message.text = "делай вариант 2"

    await comms._on_message(mock_update, MagicMock())

    sent = conv.process_message.call_args[0][0]
    assert "[REPLY_CONTEXT]" in sent
    assert "reply_to_message_id=321" in sent
    assert "Старое сообщение VITO" in sent
    assert "owner_reply=делай вариант 2" in sent


@pytest.mark.asyncio
async def test_on_message_empty(comms, mock_update):
    mock_update.message.text = "   "
    await comms._on_message(mock_update, MagicMock())
    mock_update.message.reply_text.assert_not_called()


# ── API методы ──

@pytest.mark.asyncio
async def test_send_message(comms):
    result = await comms.send_message("Hello")
    assert result is True
    comms._bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_cron_suppressed_when_disabled(comms):
    with patch("comms_agent.settings.TELEGRAM_CRON_ENABLED", False):
        result = await comms.send_message("Scheduled report", level="cron")
    assert result is True
    comms._bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_message_cron_allowed_when_enabled(comms):
    with patch("comms_agent.settings.TELEGRAM_CRON_ENABLED", True):
        result = await comms.send_message("Scheduled report", level="cron")
    assert result is True
    comms._bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_cron_suppressed_when_cancelled(comms):
    cancel_state = MagicMock()
    cancel_state.is_cancelled.return_value = True
    comms.set_modules(cancel_state=cancel_state)
    with patch("comms_agent.settings.TELEGRAM_CRON_ENABLED", True):
        result = await comms.send_message("Scheduled report", level="cron")
    assert result is True
    comms._bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_message_no_bot():
    agent = CommsAgent()
    result = await agent.send_message("test")
    assert result is True


@pytest.mark.asyncio
async def test_send_message_error(comms):
    comms._bot.send_message = AsyncMock(side_effect=Exception("Network error"))
    result = await comms.send_message("test")
    assert result is True


@pytest.mark.asyncio
async def test_send_file_not_found(comms):
    result = await comms.send_file("/nonexistent/path.pdf")
    assert result is False


@pytest.mark.asyncio
async def test_send_file_no_bot():
    agent = CommsAgent()
    result = await agent.send_file("/some/file.pdf")
    assert result is True


@pytest.mark.asyncio
async def test_send_morning_report(comms):
    result = await comms.send_morning_report("Test Report")
    assert result is True


@pytest.mark.asyncio
async def test_notify_error(comms):
    result = await comms.notify_error("test_module", "Something broke")
    assert result is True
    text = comms._bot.send_message.call_args[1]["text"]
    assert "test_module" in text


@pytest.mark.asyncio
async def test_request_approval_timeout(comms):
    result = await comms.request_approval("req_timeout", "Test approval", timeout_seconds=0)
    assert result is None
    assert "req_timeout" not in comms._pending_approvals


@pytest.mark.asyncio
async def test_request_approval_publish_channel_suppressed_when_pending(comms):
    loop = asyncio.get_running_loop()
    comms._pending_approvals["publish_twitter_prev"] = loop.create_future()
    result = await comms.request_approval("publish_twitter_new1", "Test publish approval", timeout_seconds=30)
    assert result is None
    comms._bot.send_message.assert_not_called()


def test_set_modules(comms):
    ge = MagicMock()
    llm = MagicMock()
    dl = MagicMock()
    comms.set_modules(goal_engine=ge, llm_router=llm, decision_loop=dl)
    assert comms._goal_engine is ge
    assert comms._llm_router is llm
    assert comms._decision_loop is dl


# ── Persistent keyboard ──

def test_main_keyboard():
    agent = CommsAgent()
    kb = agent._main_keyboard()
    from telegram import ReplyKeyboardMarkup
    assert isinstance(kb, ReplyKeyboardMarkup)
    # Компактное главное меню: 6 кнопок
    assert len(kb.keyboard) == 3
    texts = [btn.text for row in kb.keyboard for btn in row]
    assert "Статус" in texts
    assert "Задачи" in texts
    assert "Создать" in texts
    assert "Входы" in texts
    assert "Отчёт" in texts
    assert "Еще" in texts


@pytest.mark.asyncio
async def test_cmd_start_has_keyboard(comms, mock_update):
    await comms._cmd_start(mock_update, MagicMock())
    kwargs = mock_update.message.reply_text.call_args[1]
    assert "reply_markup" in kwargs
    from telegram import ReplyKeyboardMarkup
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)


# ── Кнопки маппинг в _on_message ──

@pytest.mark.asyncio
async def test_button_status(comms, mock_update):
    """Нажатие кнопки 'Статус' вызывает _cmd_status."""
    dl_mock = MagicMock()
    dl_mock.get_status.return_value = {"running": True, "tick_count": 0, "daily_spend": 0.0}
    ge_mock = MagicMock()
    ge_mock.get_all_goals.return_value = []
    comms.set_modules(decision_loop=dl_mock, goal_engine=ge_mock)
    mock_update.message.text = "Статус"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "VITO Status" in text


@pytest.mark.asyncio
async def test_button_goals(comms, mock_update):
    ge_mock = MagicMock()
    ge_mock.get_all_goals.return_value = []
    comms.set_modules(goal_engine=ge_mock)
    mock_update.message.text = "Цели"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Нет целей" in text


@pytest.mark.asyncio
async def test_button_legacy_main_alias(comms, mock_update):
    mock_update.message.text = "Главная"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "VITO на связи" in text


@pytest.mark.asyncio
async def test_button_with_emoji_status_alias(comms, mock_update):
    dl_mock = MagicMock()
    dl_mock.get_status.return_value = {"running": True, "tick_count": 0, "daily_spend": 0.0}
    ge_mock = MagicMock()
    ge_mock.get_all_goals.return_value = []
    comms.set_modules(decision_loop=dl_mock, goal_engine=ge_mock)
    mock_update.message.text = "📊 Статус"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "VITO Status" in text


@pytest.mark.asyncio
async def test_button_spend(comms, mock_update):
    llm_mock = MagicMock()
    llm_mock.get_daily_spend.return_value = 1.50
    comms.set_modules(llm_router=llm_mock)
    mock_update.message.text = "Расходы"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "$1.50" in text


@pytest.mark.asyncio
async def test_button_new_goal(comms, mock_update):
    mock_update.message.text = "Новая цель"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Отправь текст цели" in text


@pytest.mark.asyncio
async def test_button_approve(comms, mock_update):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["btn_req"] = future
    mock_update.message.text = "Одобрить"
    await comms._on_message(mock_update, MagicMock())
    assert future.result() is True


@pytest.mark.asyncio
async def test_button_reject(comms, mock_update):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["btn_req"] = future
    mock_update.message.text = "Отклонить"
    await comms._on_message(mock_update, MagicMock())
    assert future.result() is False


@pytest.mark.asyncio
async def test_cmd_workflow(comms, mock_update):
    ctx = MagicMock()
    ctx.args = []
    await comms._cmd_workflow(mock_update, ctx)
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Workflow" in text


@pytest.mark.asyncio
async def test_cmd_handoffs(comms, mock_update):
    await comms._cmd_handoffs(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Handoffs" in text


@pytest.mark.asyncio
async def test_cmd_pubq(comms, mock_update):
    q = MagicMock()
    q.stats.return_value = {"queued": 1, "running": 0, "done": 2, "failed": 0, "total": 3}
    q.list_jobs.return_value = [{"id": 1, "platform": "twitter", "status": "queued", "attempts": 0, "max_attempts": 3}]
    comms.set_modules(publisher_queue=q)
    await comms._cmd_pubq(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Publish Queue" in text


@pytest.mark.asyncio
async def test_cmd_pubrun(comms, mock_update):
    q = MagicMock()
    q.process_all = AsyncMock(return_value=[{"status": "done"}, {"status": "failed"}])
    comms.set_modules(publisher_queue=q)
    ctx = MagicMock()
    ctx.args = ["2"]
    await comms._cmd_pubrun(mock_update, ctx)
    text = mock_update.message.reply_text.call_args[0][0]
    assert "processed=2" in text


@pytest.mark.asyncio
async def test_cmd_webop_list(comms, mock_update):
    comms.set_modules(agent_registry=MagicMock())
    ctx = MagicMock()
    ctx.args = ["list"]
    await comms._cmd_webop(mock_update, ctx)
    text = mock_update.message.reply_text.call_args[0][0]
    assert "WebOp scenarios" in text


@pytest.mark.asyncio
async def test_cmd_skills_pending(comms, mock_update):
    reg = MagicMock()
    reg.pending_skills.return_value = [{"name": "self_improve:x", "category": "self_improve", "updated_at": "now"}]
    comms.set_modules(skill_registry=reg)
    await comms._cmd_skills_pending(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Pending skills" in text


@pytest.mark.asyncio
async def test_cmd_skills_audit(comms, mock_update):
    reg = MagicMock()
    reg.audit_coverage.return_value = 3
    reg.audit_summary.return_value = {
        "total": 10,
        "pending": 1,
        "rejected": 0,
        "high_risk": 2,
        "stable": 4,
        "top_risky": [{"name": "s1", "risk_score": 0.9, "compatibility": "review", "acceptance_status": "pending"}],
    }
    comms.set_modules(skill_registry=reg)
    await comms._cmd_skills_audit(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Skill Audit" in text


@pytest.mark.asyncio
async def test_cmd_skills_fix(comms, mock_update):
    reg = MagicMock()
    reg.remediate_high_risk.return_value = {
        "created": 2,
        "open_total": 5,
        "items": [{"skill_name": "s1", "reason": "pending_acceptance", "action": "run_tests"}],
    }
    comms.set_modules(skill_registry=reg)
    await comms._cmd_skills_fix(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Skill Remediation" in text


# ── Inline callback ──

@pytest.fixture
def mock_callback_query():
    """Мок CallbackQuery от владельца."""
    query = MagicMock()
    query.from_user = MagicMock()
    query.from_user.id = int(CommsAgent()._owner_id)
    query.data = "approve:req_inline"
    query.message = MagicMock()
    query.message.text = "Запрос на одобрение"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    return query


@pytest.mark.asyncio
async def test_handle_callback_approve(comms, mock_callback_query):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req_inline"] = future

    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "approve:req_inline"

    await comms._handle_callback(update, MagicMock())
    assert future.result() is True
    mock_callback_query.answer.assert_called_once_with("Одобрено")
    assert "Одобрено" in mock_callback_query.edit_message_text.call_args[1]["text"]


@pytest.mark.asyncio
async def test_handle_callback_reject(comms, mock_callback_query):
    future = asyncio.get_event_loop().create_future()
    comms._pending_approvals["req_inline"] = future

    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "reject:req_inline"

    await comms._handle_callback(update, MagicMock())
    assert future.result() is False
    mock_callback_query.answer.assert_called_once_with("Отклонено")


@pytest.mark.asyncio
async def test_handle_callback_already_processed(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "approve:nonexistent"

    await comms._handle_callback(update, MagicMock())
    mock_callback_query.answer.assert_called_once_with("Запрос уже обработан или не найден")


@pytest.mark.asyncio
async def test_handle_callback_stranger(comms, mock_callback_query):
    mock_callback_query.from_user.id = 999999999
    update = MagicMock()
    update.callback_query = mock_callback_query

    await comms._handle_callback(update, MagicMock())
    mock_callback_query.answer.assert_called_once_with("Доступ запрещён", show_alert=True)


@pytest.mark.asyncio
async def test_handle_callback_auth_done_verified(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "auth_done:amazon_kdp"
    comms._pending_service_auth["amazon_kdp"] = {"service": "amazon_kdp", "url": "https://kdp.amazon.com"}
    comms._verify_service_auth = AsyncMock(return_value=(True, "ok"))

    await comms._handle_callback(update, MagicMock())

    mock_callback_query.answer.assert_called_once_with("Вход подтверждён")
    assert "Вход подтверждён" in mock_callback_query.edit_message_text.call_args[1]["text"]
    assert "amazon_kdp" in comms._service_auth_confirmed


@pytest.mark.asyncio
async def test_handle_callback_auth_done_manual_fallback(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "auth_done:reddit"
    comms._pending_service_auth["reddit"] = {"service": "reddit", "url": "https://www.reddit.com/login/"}
    comms._verify_service_auth = AsyncMock(return_value=(False, "browser_only"))

    await comms._handle_callback(update, MagicMock())

    mock_callback_query.answer.assert_called_once_with("Принято")
    assert "Вход зафиксирован вручную" in mock_callback_query.edit_message_text.call_args[1]["text"]
    assert "reddit" in comms._service_auth_confirmed


@pytest.mark.asyncio
async def test_handle_callback_auth_done_manual_fallback_custom_site(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "auth_done:custom:notion.so"
    comms._pending_service_auth["custom:notion.so"] = {"service": "custom:notion.so", "url": "https://notion.so"}
    comms._verify_service_auth = AsyncMock(return_value=(False, "browser_only"))

    await comms._handle_callback(update, MagicMock())

    mock_callback_query.answer.assert_called_once_with("Принято")
    assert "Вход зафиксирован вручную" in mock_callback_query.edit_message_text.call_args[1]["text"]
    assert "custom:notion.so" in comms._service_auth_confirmed


@pytest.mark.asyncio
async def test_handle_callback_auth_done_strict_verification_amazon(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "auth_done:amazon_kdp"
    comms._pending_service_auth["amazon_kdp"] = {"service": "amazon_kdp", "url": "https://kdp.amazon.com"}
    comms._verify_service_auth = AsyncMock(return_value=(False, "probe_failed"))

    await comms._handle_callback(update, MagicMock())

    mock_callback_query.answer.assert_called_once_with("Нужно обновить сессию", show_alert=False)
    assert "Нужно обновить сессию" in mock_callback_query.edit_message_text.call_args[1]["text"]
    assert "amazon_kdp" not in comms._service_auth_confirmed


@pytest.mark.asyncio
async def test_handle_callback_auth_done_strict_remote_storage_fallback_marks_confirmed(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "auth_done:amazon_kdp"
    comms._pending_service_auth["amazon_kdp"] = {
        "service": "amazon_kdp",
        "url": "https://kdp.amazon.com",
        "mode": "remote",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    comms._verify_service_auth = AsyncMock(return_value=(False, "probe_failed"))
    comms._has_cookie_storage_state = MagicMock(return_value=(True, "storage_cookies_ok"))

    await comms._handle_callback(update, MagicMock())

    mock_callback_query.answer.assert_called_once_with("Вход подтверждён")
    assert "amazon_kdp" in comms._service_auth_confirmed


@pytest.mark.asyncio
async def test_handle_callback_auth_done_survives_noneditable_message(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "auth_done:amazon_kdp"
    comms._pending_service_auth["amazon_kdp"] = {"service": "amazon_kdp", "url": "https://kdp.amazon.com"}
    comms._verify_service_auth = AsyncMock(return_value=(True, "ok"))
    mock_callback_query.edit_message_text = AsyncMock(side_effect=TgBadRequest("Message is not modified"))
    comms.send_message = AsyncMock()

    await comms._handle_callback(update, MagicMock())

    mock_callback_query.answer.assert_called_once_with("Вход подтверждён")
    comms.send_message.assert_awaited()
    assert "amazon_kdp" in comms._service_auth_confirmed


@pytest.mark.asyncio
async def test_handle_callback_help_topic_daily(comms, mock_callback_query):
    update = MagicMock()
    update.callback_query = mock_callback_query
    mock_callback_query.data = "help_topic:daily"

    await comms._handle_callback(update, MagicMock())

    mock_callback_query.answer.assert_called_once_with("Открываю")
    edited = mock_callback_query.edit_message_text.call_args[1]["text"]
    assert "Ежедневные команды" in edited


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_forces_fresh_auth_and_requests_otp(comms):
    comms._service_auth_confirmed["amazon_kdp"] = "2026-03-04T10:00:00+00:00"
    send_reply = AsyncMock()
    comms._run_kdp_probe_stable = AsyncMock(return_value=(1, "no_session"))
    comms._run_kdp_prepare_otp = AsyncMock(return_value=(2, "OTP_REQUIRED: send code now"))
    comms._run_kdp_auto_login = AsyncMock(return_value=(1, "should_not_run"))
    comms._run_remote_auth_session = AsyncMock(return_value=(0, "REMOTE_URL=http://127.0.0.1/novnc\nVNC_PASSWORD=test"))
    handled = await comms._handle_kdp_login_flow("зайди на амазон", send_reply, with_button=True)
    assert handled is True
    comms._run_kdp_prepare_otp.assert_awaited_once()
    comms._run_kdp_auto_login.assert_not_awaited()
    comms._run_remote_auth_session.assert_not_awaited()
    assert "Нужен 6-значный код" in send_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_no_remote_fallback_when_auto_login_fails(comms):
    send_reply = AsyncMock()
    comms._run_kdp_probe_stable = AsyncMock(return_value=(1, "no_session"))
    comms._run_kdp_prepare_otp = AsyncMock(return_value=(2, "OTP_REQUIRED: send code now"))
    comms._run_remote_auth_session = AsyncMock(
        return_value=(
            0,
            "REMOTE_URL=http://127.0.0.1/novnc/vnc.html\nDIRECT_URL=http://127.0.0.1:6080/vnc.html\nVNC_PASSWORD=testpass",
        )
    )
    handled = await comms._handle_kdp_login_flow("зайди на amazon kdp", send_reply, with_button=True)
    assert handled is True
    comms._run_remote_auth_session.assert_not_awaited()
    assert "Нужен 6-значный код" in send_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_requests_otp_code(comms):
    send_reply = AsyncMock()
    comms._run_kdp_probe = AsyncMock(return_value=(2, "no_session"))
    comms._run_kdp_auto_login = AsyncMock(return_value=(2, "OTP_REQUIRED: send code now"))
    comms._run_remote_auth_session = AsyncMock(return_value=(0, "REMOTE_URL=http://127.0.0.1/novnc\nVNC_PASSWORD=test"))

    handled = await comms._handle_kdp_login_flow("зайди на amazon kdp", send_reply, with_button=True)

    assert handled is True
    assert comms._pending_kdp_otp is not None
    comms._run_remote_auth_session.assert_not_awaited()
    assert "Нужен 6-значный код" in send_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_requests_otp_code_on_mfa_url_hint(comms):
    send_reply = AsyncMock()
    comms._run_kdp_probe = AsyncMock(return_value=(2, "no_session"))
    comms._run_kdp_auto_login = AsyncMock(return_value=(2, "STEP: password_submitted https://www.amazon.com/ap/mfa?x=1"))
    comms._run_remote_auth_session = AsyncMock(return_value=(0, "REMOTE_URL=http://127.0.0.1/novnc\nVNC_PASSWORD=test"))

    handled = await comms._handle_kdp_login_flow("зайди на amazon kdp", send_reply, with_button=True)

    assert handled is True
    assert comms._pending_kdp_otp is not None
    comms._run_remote_auth_session.assert_not_awaited()
    assert "Нужен 6-значный код" in send_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_requests_otp_code_on_rc_2_without_hint(comms):
    send_reply = AsyncMock()
    comms._run_kdp_probe = AsyncMock(return_value=(2, "no_session"))
    comms._run_kdp_auto_login = AsyncMock(return_value=(2, "some other output"))
    comms._run_remote_auth_session = AsyncMock(return_value=(0, "REMOTE_URL=http://127.0.0.1/novnc\nVNC_PASSWORD=test"))

    handled = await comms._handle_kdp_login_flow("зайди на amazon kdp", send_reply, with_button=True)

    assert handled is True
    assert comms._pending_kdp_otp is not None
    comms._run_remote_auth_session.assert_not_awaited()
    assert "Нужен 6-значный код" in send_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_retries_after_transient_failure_and_requests_otp(comms):
    send_reply = AsyncMock()
    comms._run_kdp_probe_stable = AsyncMock(return_value=(1, "no_session"))
    comms._run_kdp_prepare_otp = AsyncMock(side_effect=[(9, "ERROR: prepare_otp_exception=..."), (2, "OTP_REQUIRED: send code now")])
    comms._run_remote_auth_session = AsyncMock(return_value=(0, "REMOTE_URL=http://127.0.0.1/novnc\nVNC_PASSWORD=test"))

    handled = await comms._handle_kdp_login_flow("зайди на amazon kdp", send_reply, with_button=True)

    assert handled is True
    assert comms._run_kdp_prepare_otp.await_count == 2
    comms._run_remote_auth_session.assert_not_awaited()
    assert "Нужен 6-значный код" in send_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_fallback_enables_forced_otp(comms):
    send_reply = AsyncMock()
    comms._run_kdp_probe_stable = AsyncMock(return_value=(1, "no_session"))
    comms._run_kdp_prepare_otp = AsyncMock(
        side_effect=[
            (9, "ERROR: prepare_otp_exception"),
            (9, "ERROR: prepare_otp_exception_retry"),
            (9, "ERROR: prepare_otp_exception_retry2"),
            (9, "ERROR: prepare_otp_exception_retry3"),
            (9, "ERROR: prepare_otp_exception_retry4"),
        ]
    )
    comms._run_remote_auth_session = AsyncMock(return_value=(0, "REMOTE_URL=http://127.0.0.1/novnc\nVNC_PASSWORD=test"))

    handled = await comms._handle_kdp_login_flow("зайди на amazon kdp", send_reply, with_button=True)

    assert handled is True
    assert comms._pending_kdp_otp is not None
    assert bool(comms._pending_kdp_otp.get("forced")) is True
    assert "Пришли 6-значный код" in send_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_otp_branch_accepts_probe_success_after_login_fail(comms):
    send_reply = AsyncMock()
    comms._pending_kdp_otp = {"requested_at": "2026-03-04T21:00:00+00:00"}
    comms._run_kdp_auto_login = AsyncMock(return_value=(9, "auto_login_exception"))
    comms._run_kdp_probe_stable = AsyncMock(return_value=(0, "ok"))

    handled = await comms._handle_kdp_login_flow("123456", send_reply, with_button=True)

    assert handled is True
    assert comms._pending_kdp_otp is None
    assert "amazon_kdp" in comms._service_auth_confirmed
    assert "live-check OK" in send_reply.call_args_list[-1].args[0]


@pytest.mark.asyncio
async def test_handle_kdp_login_flow_otp_branch_keeps_pending_on_failure(comms):
    send_reply = AsyncMock()
    comms._pending_kdp_otp = {"requested_at": "2026-03-04T21:00:00+00:00"}
    comms._run_kdp_probe_stable = AsyncMock(side_effect=[(1, "fail"), (1, "fail"), (1, "fail")])
    comms._run_kdp_auto_login = AsyncMock(side_effect=[(9, "auto_login_exception"), (9, "auto_login_exception_retry")])

    handled = await comms._handle_kdp_login_flow("654321", send_reply, with_button=True)

    assert handled is True
    assert comms._pending_kdp_otp is not None
    assert bool(comms._pending_kdp_otp.get("retry")) is True
    assert "Пришли новый 6-значный код" in send_reply.call_args_list[-1].args[0]


@pytest.mark.asyncio
async def test_on_message_login_request_starts_generic_service_auth(comms, mock_update):
    mock_update.message.text = "зайди в реддит"
    comms._start_service_auth_flow = AsyncMock(return_value=True)
    comms._handle_kdp_login_flow = AsyncMock(return_value=False)

    await comms._on_message(mock_update, MagicMock())

    comms._start_service_auth_flow.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_message_twitter_login_request_starts_generic_service_auth(comms, mock_update):
    mock_update.message.text = "зайди на твиттер"
    comms._start_service_auth_flow = AsyncMock(return_value=True)
    comms._handle_kdp_login_flow = AsyncMock(return_value=False)

    await comms._on_message(mock_update, MagicMock())

    assert comms._start_service_auth_flow.await_args.args[0] == "twitter"


@pytest.mark.asyncio
async def test_on_message_threads_login_request_starts_generic_service_auth(comms, mock_update):
    mock_update.message.text = "зайди в threads"
    comms._start_service_auth_flow = AsyncMock(return_value=True)
    comms._handle_kdp_login_flow = AsyncMock(return_value=False)

    await comms._on_message(mock_update, MagicMock())

    assert comms._start_service_auth_flow.await_args.args[0] == "threads"


@pytest.mark.asyncio
async def test_on_message_custom_site_login_request_starts_generic_service_auth(comms, mock_update):
    mock_update.message.text = "зайди на notion.so"
    comms._start_service_auth_flow = AsyncMock(return_value=True)
    comms._handle_kdp_login_flow = AsyncMock(return_value=False)

    await comms._on_message(mock_update, MagicMock())

    assert comms._start_service_auth_flow.await_args.args[0] == "custom:notion.so"


@pytest.mark.asyncio
async def test_on_message_custom_site_login_request_ukr_net_alias(comms, mock_update):
    mock_update.message.text = "зайди на укр нет"
    comms._start_service_auth_flow = AsyncMock(return_value=True)
    comms._handle_kdp_login_flow = AsyncMock(return_value=False)

    await comms._on_message(mock_update, MagicMock())

    assert comms._start_service_auth_flow.await_args.args[0] == "custom:ukr.net"


@pytest.mark.asyncio
async def test_on_message_custom_site_login_request_ukr_pravda_alias(comms, mock_update):
    mock_update.message.text = "зайди на укрправду"
    comms._start_service_auth_flow = AsyncMock(return_value=True)
    comms._handle_kdp_login_flow = AsyncMock(return_value=False)

    await comms._on_message(mock_update, MagicMock())

    assert comms._start_service_auth_flow.await_args.args[0] == "custom:www.pravda.com.ua"


@pytest.mark.asyncio
async def test_on_message_login_intent_has_priority_over_inventory_context(comms, mock_update):
    mock_update.message.text = "зайди на амазон и проверь товары"
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)
    comms._handle_kdp_login_flow = AsyncMock(return_value=True)

    await comms._on_message(mock_update, MagicMock())

    comms._handle_kdp_login_flow.assert_awaited_once()
    conv.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_login_and_inventory_combined_uses_inventory_when_confirmed(comms, mock_update):
    mock_update.message.text = "зайди на мой амазон, проверь наличие товаров"
    comms._service_auth_confirmed["amazon_kdp"] = datetime.now(timezone.utc).isoformat()
    comms._run_kdp_probe = AsyncMock(return_value=(0, "ok"))
    comms._run_kdp_inventory_probe = AsyncMock(
        return_value=(0, '{"ok": true, "products_count": 1, "items": ["Book X"]}')
    )
    comms._handle_kdp_login_flow = AsyncMock(return_value=False)
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)

    await comms._on_message(mock_update, MagicMock())

    sent = mock_update.message.reply_text.call_args[0][0]
    assert "Товаров/книг: 1" in sent
    comms._handle_kdp_login_flow.assert_not_called()
    conv.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_contextual_service_status(comms, mock_update):
    comms._last_service_context = "twitter"
    mock_update.message.text = "покажи статус"
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)

    await comms._on_message(mock_update, MagicMock())

    sent = mock_update.message.reply_text.call_args[0][0]
    assert "Twitter" in sent
    conv.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_contextual_service_status_plain_status(comms, mock_update):
    comms._last_service_context = "amazon_kdp"
    comms._last_service_context_at = datetime.now(timezone.utc).isoformat()
    comms._run_kdp_probe = AsyncMock(return_value=(0, "ok"))
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)
    mock_update.message.text = "статус"

    await comms._on_message(mock_update, MagicMock())

    sent = mock_update.message.reply_text.call_args[0][0]
    assert "Amazon KDP" in sent
    conv.process_message.assert_not_called()


def test_detect_contextual_service_status_uses_pending_auth_when_no_fresh_context(comms):
    comms._last_service_context = ""
    comms._last_service_context_at = ""
    comms._pending_service_auth["amazon_kdp"] = {"service": "amazon_kdp"}
    assert comms._detect_contextual_service_status_request("статус аккаунта") == "amazon_kdp"
    assert comms._detect_contextual_service_status_request("состояние аккаунта") == "amazon_kdp"


@pytest.mark.asyncio
async def test_format_service_auth_status_live_amazon_probe_fail_with_cached_confirmed(comms):
    comms._service_auth_confirmed["amazon_kdp"] = "2026-03-04T01:00:00+00:00"
    comms._run_kdp_probe = AsyncMock(return_value=(1, "fail"))
    text = await comms._format_service_auth_status_live("amazon_kdp")
    assert "live-check" in text.lower()


@pytest.mark.asyncio
async def test_on_message_contextual_service_inventory_uses_service_context(comms, mock_update):
    comms._last_service_context = "twitter"
    comms._last_service_context_at = datetime.now(timezone.utc).isoformat()
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)
    reg = MagicMock()
    reg.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": {"twitter": {"products_count": 3, "sales": 1}}})())
    comms.set_modules(agent_registry=reg)
    mock_update.message.text = "проверь есть ли там товары"

    await comms._on_message(mock_update, MagicMock())

    sent = mock_update.message.reply_text.call_args[0][0]
    assert "Twitter" in sent
    assert "Товаров: 3" in sent
    conv.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_contextual_service_inventory_amazon_requires_live_session(comms, mock_update):
    comms._last_service_context = "amazon_kdp"
    comms._last_service_context_at = datetime.now(timezone.utc).isoformat()
    comms._run_kdp_probe = AsyncMock(return_value=(1, "fail"))
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)
    reg = MagicMock()
    reg.dispatch = AsyncMock()
    comms.set_modules(agent_registry=reg)
    mock_update.message.text = "проверь есть ли там товары"

    await comms._on_message(mock_update, MagicMock())

    sent = mock_update.message.reply_text.call_args[0][0]
    assert "не вижу активной сессии" in sent.lower()


def test_detect_contextual_service_inventory_uses_pending_auth_when_no_fresh_context(comms):
    comms._last_service_context = ""
    comms._last_service_context_at = ""
    comms._pending_service_auth["etsy"] = {"service": "etsy"}
    assert comms._detect_contextual_service_inventory_request("проверь товары там") == "etsy"


@pytest.mark.asyncio
async def test_on_message_auth_done_text_strict_remote_storage_fallback(comms, mock_update):
    mock_update.message.text = "я вошел"
    comms._pending_service_auth["amazon_kdp"] = {
        "service": "amazon_kdp",
        "mode": "remote",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    comms._verify_service_auth = AsyncMock(return_value=(False, "probe_failed"))
    comms._has_cookie_storage_state = MagicMock(return_value=(True, "storage_cookies_ok"))
    comms._conversation_engine = MagicMock()
    comms._conversation_engine.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})

    await comms._on_message(mock_update, MagicMock())

    sent = mock_update.message.reply_text.call_args[0][0]
    assert "Вход подтверждён: Amazon KDP" in sent
    assert "amazon_kdp" in comms._service_auth_confirmed
    comms._conversation_engine.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_format_service_inventory_snapshot_amazon_uses_kdp_inventory_probe(comms):
    comms._run_kdp_probe = AsyncMock(return_value=(0, "ok"))
    comms._run_kdp_inventory_probe = AsyncMock(
        return_value=(0, '{"ok": true, "products_count": 2, "items": ["Book A", "Book B"]}')
    )
    reg = MagicMock()
    reg.dispatch = AsyncMock()
    comms.set_modules(agent_registry=reg)

    text = await comms._format_service_inventory_snapshot("amazon_kdp")

    assert "Товаров/книг: 2" in text
    assert "Book A" in text
    reg.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_format_service_inventory_snapshot_amazon_filters_noise_items(comms):
    comms._run_kdp_probe = AsyncMock(return_value=(0, "ok"))
    comms._run_kdp_inventory_probe = AsyncMock(
        return_value=(
            0,
            '{"ok": true, "products_count": 3, "items": ["How would you rate your experience using this page?", "VITO TEST DRAFT 1", "Visit our help center for resources to common issues"]}',
        )
    )
    reg = MagicMock()
    reg.dispatch = AsyncMock()
    comms.set_modules(agent_registry=reg)

    text = await comms._format_service_inventory_snapshot("amazon_kdp")

    assert "Товаров/книг: 1" in text
    assert "VITO TEST DRAFT 1" in text
    assert "How would you rate your experience" not in text


@pytest.mark.asyncio
async def test_on_message_contextual_inventory_has_priority_over_brainstorm(comms, mock_update):
    comms._last_service_context = "amazon_kdp"
    comms._last_service_context_at = datetime.now(timezone.utc).isoformat()
    comms._run_kdp_probe = AsyncMock(return_value=(1, "fail"))
    comms._maybe_brainstorm_from_text = AsyncMock(return_value=True)
    conv = MagicMock()
    conv.process_message = AsyncMock(return_value={"response": "SHOULD_NOT_BE_USED"})
    comms.set_modules(conversation_engine=conv)
    mock_update.message.text = "проверь есть ли там товары"

    with patch("comms_agent.settings.AUTONOMY_MAX_MODE", True):
        await comms._on_message(mock_update, MagicMock())

    comms._maybe_brainstorm_from_text.assert_not_called()
    conv.process_message.assert_not_called()


def test_detect_contextual_inventory_request_for_account_phrase(comms):
    comms._last_service_context = "amazon_kdp"
    comms._last_service_context_at = datetime.now(timezone.utc).isoformat()
    assert comms._detect_contextual_service_inventory_request("проверь аккаунт") == "amazon_kdp"


def test_detect_service_login_request_kofi_with_space(comms):
    assert comms._detect_service_login_request("зайди на ко фи") == "kofi"


def test_detect_contextual_status_without_fresh_context_returns_empty(comms):
    comms._last_service_context = ""
    assert comms._detect_contextual_service_status_request("статус") == ""


def test_detect_contextual_inventory_without_fresh_context_returns_empty(comms):
    comms._last_service_context = ""
    assert comms._detect_contextual_service_inventory_request("проверь товары") == ""


def test_detect_contextual_inventory_does_not_capture_create_publish_intents(comms):
    comms._last_service_context = "etsy"
    comms._last_service_context_at = datetime.now(timezone.utc).isoformat()
    assert comms._detect_contextual_service_inventory_request("создай листинг на этси") == ""
    assert comms._detect_contextual_service_inventory_request("опубликуй товар на gumroad") == ""
    assert comms._detect_contextual_service_inventory_request("create listing on etsy") == ""


def test_humanize_owner_text_strips_technical_noise(comms):
    src = (
        "Вот план, что думаешь?\n"
        "Принял: задача создана\n"
        "Принято.\n"
        "active task fixed\n"
        "job_id=17\n"
        "task_id=abc123\n"
        "{\"goal_id\":\"g1\"}\n"
        "Дам результат."
    )
    out = comms._humanize_owner_text(src)
    assert "вот план" not in out.lower()
    assert "принял:" not in out.lower()
    assert "job_id" not in out.lower()
    assert "task_id" not in out.lower()
    assert "goal_id" not in out.lower()
    assert "Дам результат" in out


# ── request_approval с inline кнопками ──

@pytest.mark.asyncio
async def test_request_approval_inline_buttons(comms):
    """request_approval отправляет сообщение с inline-кнопками."""
    # Запускаем с timeout=0, чтобы сразу получить результат
    result = await comms.request_approval("req_btn", "Approve this?", timeout_seconds=0)
    assert result is None  # timeout

    # Проверяем что send_message вызван с inline keyboard
    call_kwargs = comms._bot.send_message.call_args[1]
    from telegram import InlineKeyboardMarkup
    assert isinstance(call_kwargs["reply_markup"], InlineKeyboardMarkup)
    buttons = call_kwargs["reply_markup"].inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[0].text == "Одобрить"
    assert buttons[1].text == "Отклонить"
    assert "approve:req_btn" in buttons[0].callback_data
    assert "reject:req_btn" in buttons[1].callback_data
