"""Тесты comms_agent.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comms_agent import CommsAgent


@pytest.fixture
def comms():
    """CommsAgent с мок-ботом."""
    agent = CommsAgent()
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
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = ""
    return update


@pytest.fixture
def stranger_update():
    """Мок Telegram Update от чужого пользователя."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 999999999
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
async def test_cmd_status(comms, mock_update):
    dl_mock = MagicMock()
    dl_mock.get_status.return_value = {"running": True, "tick_count": 5, "daily_spend": 1.23}
    ge_mock = MagicMock()
    ge_mock.get_stats.return_value = {"total": 3, "completed": 1, "executing": 1, "pending": 1}
    comms.set_modules(goal_engine=ge_mock, decision_loop=dl_mock)

    await comms._cmd_status(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "VITO Status" in text
    assert "работает" in text


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
async def test_cmd_goal_create(comms, mock_update):
    from goal_engine import GoalEngine
    ge = GoalEngine()
    comms.set_modules(goal_engine=ge)

    mock_update.message.text = "/goal Заработать на Etsy шаблонах"
    await comms._cmd_goal(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Цель создана" in text
    assert len(ge._goals) == 1


@pytest.mark.asyncio
async def test_cmd_goal_empty(comms, mock_update):
    ge = MagicMock()
    comms.set_modules(goal_engine=ge)
    mock_update.message.text = "/goal"
    await comms._cmd_goal(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Использование" in text


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
async def test_on_message_regular(comms, mock_update):
    mock_update.message.text = "Сделай мне продукт"
    await comms._on_message(mock_update, MagicMock())
    text = mock_update.message.reply_text.call_args[0][0]
    assert "Не понял" in text


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
    # 3 ряда по 2 кнопки
    assert len(kb.keyboard) == 3
    texts = [btn.text for row in kb.keyboard for btn in row]
    assert "Статус" in texts
    assert "Цели" in texts
    assert "Расходы" in texts
    assert "Одобрить" in texts
    assert "Отклонить" in texts
    assert "Новая цель" in texts


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
    comms.set_modules(decision_loop=dl_mock)
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
