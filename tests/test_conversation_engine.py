"""Тесты для ConversationEngine."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from conversation_engine import ConversationEngine, Intent, Turn, MAX_CONTEXT_TURNS
from modules.cancel_state import CancelState
from modules.conversation_memory import ConversationMemory
from modules.owner_task_state import OwnerTaskState


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
        assert engine._detect_intent_rules("Привет, как дела?") is not None

    def test_goal_request_intent(self, engine):
        # "Сделай" is a goal request keyword
        assert engine._detect_intent_rules("Сделай отчёт") == Intent.GOAL_REQUEST

    def test_goal_request_intent_with_typos(self, engine):
        assert engine._detect_intent_rules("сдлай атчот по трендам") == Intent.GOAL_REQUEST

    def test_goal_request_intent_mixed_language(self, engine):
        assert engine._detect_intent_rules("pls найди trends for gumroad") == Intent.GOAL_REQUEST

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

    def test_extract_platform_key_supports_kofi_hyphen_ru(self, engine):
        assert engine._extract_platform_key("создай товар на ко-фи") == "kofi"

    def test_extract_platform_key_supports_kofi_space_ru(self, engine):
        assert engine._extract_platform_key("создай товар на ко фи") == "kofi"

    def test_imperative_detection_supports_login_verbs(self, engine):
        assert engine._looks_like_imperative_request("зайди на амазон") is True

    @pytest.mark.asyncio
    async def test_deterministic_platform_route_for_twitter_post(self, engine):
        engine._execute_actions = AsyncMock(return_value="ok")
        out = await engine._deterministic_owner_route("создай пост в твиттер с анонсом продукта")
        assert out is not None
        assert out.get("intent") == Intent.SYSTEM_ACTION.value
        actions = out.get("actions") or []
        assert actions and actions[0].get("action") == "run_platform_task"
        assert actions[0].get("params", {}).get("platform") == "twitter"


class TestProcessMessage:
    @pytest.mark.asyncio
    async def test_cancelled_state_blocks_processing(self, mock_llm_router, mock_memory, tmp_path):
        cancel_path = tmp_path / "cancel_state.json"
        cancel_state = CancelState(path=cancel_path)
        cancel_state.cancel("test")
        engine = ConversationEngine(
            llm_router=mock_llm_router,
            memory=mock_memory,
            cancel_state=cancel_state,
        )

        result = await engine.process_message("Сделай отчёт")
        assert result["intent"] == "conversation"
        assert "паузе" in result["response"]

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
    async def test_process_message_returns_nlu_tones(self, engine):
        engine.llm_router.call_llm = AsyncMock(side_effect=[
            "CONVERSATION",
            "Понял, исправляю.",
        ])
        result = await engine.process_message("это не работает, срочно почини")
        assert result["intent"] == "system_action"
        assert "frustrated" in result.get("nlu_tones", [])
        assert "urgent" in result.get("nlu_tones", [])

    @pytest.mark.asyncio
    async def test_question_gumroad_stats_uses_live_sales_check(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        sales = {"gumroad": {"platform": "gumroad", "sales": 7, "revenue": 123.45, "products_count": 3}}
        registry.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": sales})())
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        result = await engine._handle_question("какая сейчас статистика на гумроад?")
        assert result["intent"] == "question"
        assert "Gumroad (live)" in result["response"]
        assert "Продажи: 7" in result["response"]

    @pytest.mark.asyncio
    async def test_owner_name_is_remembered_and_returned(self, mock_llm_router, mock_memory):
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)
        engine.llm_router.call_llm = AsyncMock(return_value="ok")
        await engine.process_message("меня зовут Тарас")
        result = await engine._handle_question("как меня зовут?")
        assert result["intent"] == "question"
        assert "Тарас" in result["response"]

    @pytest.mark.asyncio
    async def test_owner_name_single_word_reply_is_remembered(self, mock_llm_router, mock_memory):
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)
        engine.llm_router.call_llm = AsyncMock(return_value="ok")
        engine._add_turn("assistant", "Как тебя зовут?")
        await engine.process_message("Виталий")
        result = await engine._handle_question("как меня зовут?")
        assert result["intent"] == "question"
        assert "Виталий" in result["response"]

    @pytest.mark.asyncio
    async def test_deterministic_trend_route_executes_without_llm(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        engine._execute_actions = AsyncMock(return_value="[scan_trends][status=completed] done")
        result = await engine.process_message("срочно найди тренды цифровых продуктов")
        assert result["intent"] == "system_action"
        assert "сканирование трендов" in result["response"].lower()
        engine._execute_actions.assert_called_once()
        engine.llm_router.call_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_deterministic_deep_research_route_executes_without_llm(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        engine._execute_actions = AsyncMock(return_value="[run_deep_research] done")
        result = await engine.process_message("проведи глубокое исследование ниши digital planners")
        assert result["intent"] == "system_action"
        assert "глубокое исследование" in result["response"].lower()
        engine._execute_actions.assert_called_once()
        engine.llm_router.call_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_deterministic_platform_route_executes_without_llm(self, mock_llm_router, mock_memory):
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=MagicMock())
        engine._execute_actions = AsyncMock(return_value="amazon_kdp: ok")
        result = await engine.process_message("зайди на амазон и проверь товары")
        assert result["intent"] == "system_action"
        assert "amazon_kdp" in result["response"].lower()
        engine._execute_actions.assert_called_once()
        engine.llm_router.call_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_deterministic_printful_etsy_route_executes_without_llm(self, mock_llm_router, mock_memory):
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=MagicMock())
        engine._execute_actions = AsyncMock(return_value="Printful->Etsy: ok")
        result = await engine.process_message("создай листинг через принтфул и размести на этси")
        assert result["intent"] == "system_action"
        assert "printful" in result["response"].lower()
        engine._execute_actions.assert_called_once()
        engine.llm_router.call_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_platform_task_uses_recipe_executor_via_comms(self, mock_llm_router, mock_memory):
        comms = MagicMock()
        comms._run_recipe_direct = AsyncMock(
            return_value={
                "status": "accepted",
                "result": {
                    "status": "draft",
                    "listing_id": "12345",
                    "url": "https://www.etsy.com/listing/12345",
                },
            }
        )
        engine = ConversationEngine(
            llm_router=mock_llm_router,
            memory=mock_memory,
            agent_registry=MagicMock(),
            comms=comms,
        )
        out = await engine._dispatch_action(
            "run_platform_task",
            {"platform": "etsy", "request": "создай черновик листинга на этси и заполни все поля"},
        )
        assert "publish-flow" in out
        assert "12345" in out
        comms._run_recipe_direct.assert_awaited_once_with(
            "etsy_publish",
            live=True,
            request_text="создай черновик листинга на этси и заполни все поля",
        )

    @pytest.mark.asyncio
    async def test_deterministic_network_check_route(self, engine):
        result = await engine.process_message("проверь доступ к интернету")
        assert result["intent"] == "question"
        assert "Проверка сети" in result["response"]

    @pytest.mark.asyncio
    async def test_deterministic_etsy_oauth_route(self, engine, monkeypatch):
        from platforms import etsy as etsy_mod
        monkeypatch.setattr(
            etsy_mod.EtsyPlatform,
            "start_oauth2_pkce",
            AsyncMock(return_value={"auth_url": "https://www.etsy.com/oauth/connect?x=1", "redirect_uri": "http://localhost/cb"}),
        )
        result = await engine.process_message("подключи etsy oauth")
        assert result["intent"] == "system_action"
        assert "Etsy OAuth подготовлен" in result["response"]

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

    @pytest.mark.asyncio
    async def test_system_action_requires_confirmation_and_no_auto_execute(self, engine, monkeypatch):
        monkeypatch.setattr("conversation_engine.settings.AUTONOMY_MAX_MODE", False, raising=False)
        engine._execute_actions = AsyncMock(return_value="done")
        result = await engine.process_message("исправь интеграцию")
        assert result["intent"] == "system_action"
        assert result.get("needs_confirmation") is True
        assert result.get("actions")
        engine._execute_actions.assert_not_called()

    @pytest.mark.asyncio
    async def test_system_action_llm_actions_marked_for_confirmation(self, engine):
        engine.llm_router.call_llm = AsyncMock(return_value='{"response":"Ок","actions":[{"action":"scan_trends","params":{}}]}')
        engine._execute_actions = AsyncMock(return_value="done")
        result = await engine.process_message("запусти агент и проверь логи")
        assert result["intent"] == "system_action"
        assert result.get("needs_confirmation") is False
        engine._execute_actions.assert_called_once()

    @pytest.mark.asyncio
    async def test_system_action_trend_scan_executes_without_confirmation(self, engine):
        engine._execute_actions = AsyncMock(return_value="[scan_trends] done")
        result = await engine._handle_system_action("найди тренды цифровых продуктов")
        assert result["intent"] == "system_action"
        assert result.get("needs_confirmation") is False
        engine._execute_actions.assert_called_once()

    @pytest.mark.asyncio
    async def test_system_action_learn_service_requires_confirmation_when_not_autonomy_max(self, engine, monkeypatch):
        monkeypatch.setattr("conversation_engine.settings.AUTONOMY_MAX_MODE", False, raising=False)
        result = await engine._handle_system_action("изучи сервис amazon kdp")
        assert result["intent"] == "system_action"
        assert result.get("needs_confirmation") is True

    @pytest.mark.asyncio
    async def test_system_action_learn_service_no_confirmation_in_autonomy_max(self, engine, monkeypatch):
        monkeypatch.setattr("conversation_engine.settings.AUTONOMY_MAX_MODE", True, raising=False)
        result = await engine._handle_system_action("изучи сервис amazon kdp")
        assert result["intent"] == "system_action"
        assert result.get("needs_confirmation") is False

    @pytest.mark.asyncio
    async def test_system_action_autonomous_execute_default(self, engine, monkeypatch):
        monkeypatch.setattr("conversation_engine.settings.AUTONOMY_AUTO_EXECUTE_REQUESTS", True, raising=False)
        result = await engine._handle_system_action("подготовь контент и опубликуй")
        assert result["intent"] == "system_action"
        assert result.get("actions")
        assert result["actions"][0]["action"] == "autonomous_execute"

    @pytest.mark.asyncio
    async def test_dispatch_action_run_product_pipeline(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        registry.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": {"steps": [{"ok": True}]}})())
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        msg = await engine._dispatch_action(
            "run_product_pipeline",
            {"topic": "AI templates", "platforms": ["gumroad"], "auto_publish": False},
        )
        assert "Product pipeline завершён" in msg

    @pytest.mark.asyncio
    async def test_dispatch_action_run_printful_etsy_sync(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        registry.dispatch = AsyncMock(
            side_effect=[
                type("R1", (), {"success": True, "output": {"platform": "printful", "status": "created"}})(),
                type("R2", (), {"success": True, "output": {"etsy": {"listings": 1}}})(),
            ]
        )
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        msg = await engine._dispatch_action("run_printful_etsy_sync", {"topic": "POD test", "auto_publish": True})
        assert "Printful→Etsy" in msg

    @pytest.mark.asyncio
    async def test_dispatch_action_run_deep_research_formats_sources_and_quality(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        registry.dispatch = AsyncMock(
            side_effect=[
                type(
                    "R",
                    (),
                    {
                        "success": True,
                        "output": "Long report body",
                        "metadata": {
                            "executive_summary": "Summary line",
                            "data_sources": ["reddit", "google_trends"],
                            "top_ideas": [
                                {"rank": 1, "title": "Prompt Pack", "score": 89, "platform": "gumroad"},
                                {"rank": 2, "title": "Planner", "score": 81, "platform": "etsy"},
                            ],
                            "recommended_product": {"title": "Prompt Pack", "score": 89, "platform": "gumroad", "why_now": "rising intent"},
                        },
                        "error": "",
                    },
                )(),
                type("Q", (), {"success": True, "output": {"approved": True, "score": 88}, "error": ""})(),
            ]
        )
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        msg = await engine._dispatch_action("run_deep_research", {"topic": "digital planners"})
        assert "Глубокое исследование готово" in msg
        assert "Источники: google_trends, reddit" in msg
        assert "score=88" in msg
        assert "Топ-варианты:" in msg
        assert "Prompt Pack" in msg

    @pytest.mark.asyncio
    async def test_dispatch_agent_research_adds_quality_gate(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        registry.dispatch = AsyncMock(
            side_effect=[
                type("R", (), {"success": True, "output": "research done", "error": ""})(),
                type("Q", (), {"success": True, "output": {"approved": True, "score": 9}, "error": ""})(),
            ]
        )
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        msg = await engine._dispatch_action("dispatch_agent", {"task_type": "research", "step": "test"})
        assert "Агент выполнил" in msg
        assert "Quality gate: ok(" in msg

    @pytest.mark.asyncio
    async def test_dispatch_action_autonomous_execute_success_first_try(self, mock_llm_router, mock_memory):
        registry = MagicMock()
        registry.dispatch = AsyncMock(return_value=type("R", (), {"success": True, "output": "done", "error": ""})())
        registry.get = MagicMock(return_value=None)
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=registry)
        msg = await engine._dispatch_action("autonomous_execute", {"request": "сделай seo оптимизацию"})
        assert "Задача выполнена" in msg

    @pytest.mark.asyncio
    async def test_pick_capability_from_memory_prefers_successful_skill(self, mock_llm_router, mock_memory):
        mock_memory.search_skills.return_value = [
            {"task_type": "research", "success_count": 1, "fail_count": 3},
            {"task_type": "listing_seo_pack", "success_count": 5, "fail_count": 0},
        ]
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, agent_registry=MagicMock())
        cap = engine._pick_capability_from_memory("сделай seo для листинга")
        assert cap == "listing_seo_pack"

    @pytest.mark.asyncio
    async def test_system_action_publish_now_routes_to_auto_publish(self, engine, monkeypatch):
        monkeypatch.setattr("conversation_engine.settings.AUTONOMY_MAX_MODE", True, raising=False)
        result = await engine._handle_system_action("ок публикуй товар на gumroad")
        assert result["intent"] == "system_action"
        assert result["actions"][0]["action"] == "run_product_pipeline"
        assert result["actions"][0]["params"]["auto_publish"] is True

    @pytest.mark.asyncio
    async def test_owner_task_state_persists_after_goal_then_question(self, mock_llm_router, mock_memory, tmp_path):
        owner_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
        engine = ConversationEngine(
            llm_router=mock_llm_router,
            memory=mock_memory,
            owner_task_state=owner_state,
        )
        mock_llm_router.call_llm = AsyncMock(side_effect=["{}", "Ответ"])
        await engine.process_message("сделай отчет по продажам")
        active = owner_state.get_active()
        assert active is not None
        assert "сделай отчет" in str(active.get("text", "")).lower()
        await engine.process_message("какой у нас бюджет?")
        active2 = owner_state.get_active()
        assert active2 is not None
        assert active2.get("text") == active.get("text")

    @pytest.mark.asyncio
    async def test_owner_task_state_preserve_notice_on_new_system_request(self, mock_llm_router, mock_memory, tmp_path):
        owner_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
        owner_state.set_active("первая задача", intent="goal_request")
        engine = ConversationEngine(
            llm_router=mock_llm_router,
            memory=mock_memory,
            owner_task_state=owner_state,
        )
        result = await engine.process_message("исправь интеграцию")
        assert result["intent"] == "system_action"
        assert "/task_replace" not in result.get("response", "")
        active = owner_state.get_active()
        assert active is not None
        assert "первая задача" in active.get("text", "")


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

    def test_context_persists_to_disk_and_reloads(self, mock_llm_router, mock_memory, tmp_path):
        mem_path = tmp_path / "conversation_history.json"
        cm = ConversationMemory(path=mem_path, limit=20)
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, conversation_memory=cm)
        engine._add_turn("user", "Первое сообщение", Intent.CONVERSATION)
        engine._add_turn("assistant", "Ответ", Intent.CONVERSATION)

        reloaded = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, conversation_memory=cm)
        formatted = reloaded._format_context()
        assert "Первое сообщение" in formatted
        assert "Ответ" in formatted

    def test_context_persists_per_session(self, mock_llm_router, mock_memory, tmp_path):
        mem_path = tmp_path / "conversation_history.json"
        cm = ConversationMemory(path=mem_path, limit=20)
        engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, conversation_memory=cm)
        engine.set_session("chat_a")
        engine._add_turn("user", "Сообщение A", Intent.CONVERSATION)
        engine._add_turn("assistant", "Ответ A", Intent.CONVERSATION)
        engine.set_session("chat_b")
        engine._add_turn("user", "Сообщение B", Intent.CONVERSATION)

        reloaded = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, conversation_memory=cm)
        reloaded.set_session("chat_a")
        formatted_a = reloaded._format_context()
        reloaded.set_session("chat_b")
        formatted_b = reloaded._format_context()
        assert "Сообщение A" in formatted_a
        assert "Ответ A" in formatted_a
        assert "Сообщение B" not in formatted_a
        assert "Сообщение B" in formatted_b

    def test_format_context_uses_configured_turns(self, engine, monkeypatch):
        monkeypatch.setattr("conversation_engine.settings.CONVERSATION_CONTEXT_TURNS", 5)
        for i in range(12):
            engine._add_turn("user", f"u{i}")
        formatted = engine._format_context()
        assert "u11" in formatted
        assert "u7" in formatted
        assert "u6" not in formatted


@pytest.mark.asyncio
async def test_handle_conversation_includes_owner_task_focus(mock_llm_router, mock_memory, tmp_path):
    owner_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_state.set_active("подготовить лендинг", intent="goal_request")
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, owner_task_state=owner_state)
    mock_llm_router.call_llm = AsyncMock(return_value="ok")
    await engine._handle_conversation("какой следующий шаг?")
    args = mock_llm_router.call_llm.call_args.kwargs
    prompt = args.get("prompt", "")
    assert "Фокус владельца" in prompt
    assert "подготовить лендинг" in prompt


@pytest.mark.asyncio
async def test_handle_system_action_includes_history_and_owner_focus(mock_llm_router, mock_memory, tmp_path):
    owner_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_state.set_active("закрыть баг в телеграм", intent="system_action")
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, owner_task_state=owner_state)
    engine._add_turn("user", "предыдущее сообщение")
    mock_llm_router.call_llm = AsyncMock(return_value='{"response":"ok","actions":[]}')
    await engine._handle_system_action("проверь логи")
    prompt = mock_llm_router.call_llm.call_args.kwargs.get("prompt", "")
    assert "История разговора" in prompt
    assert "предыдущее сообщение" in prompt
    assert "Фокус владельца" in prompt
    assert "закрыть баг в телеграм" in prompt


@pytest.mark.asyncio
async def test_handle_goal_request_includes_history_and_owner_focus(mock_llm_router, mock_memory, tmp_path):
    owner_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_state.set_active("выпустить продукт", intent="goal_request")
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, owner_task_state=owner_state)
    engine._add_turn("user", "контекст перед задачей")
    mock_llm_router.call_llm = AsyncMock(return_value='{"goal_title":"t","goal_description":"d","confirmation":"c","needs_approval":true}')
    await engine._handle_goal_request("сделай лендинг")
    prompt = mock_llm_router.call_llm.call_args.kwargs.get("prompt", "")
    assert "История разговора" in prompt
    assert "контекст перед задачей" in prompt
    assert "Фокус владельца" in prompt
    assert "выпустить продукт" in prompt


@pytest.mark.asyncio
async def test_handle_goal_request_auto_approve_enabled(monkeypatch, mock_llm_router, mock_memory):
    monkeypatch.setattr("conversation_engine.settings.OWNER_AUTO_APPROVE_GOALS", True, raising=False)
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)
    mock_llm_router.call_llm = AsyncMock(return_value='{"goal_title":"t","goal_description":"d","confirmation":"c"}')
    result = await engine._handle_goal_request("сделай лендинг")
    assert result["create_goal"] is True
    assert result["needs_approval"] is False


@pytest.mark.asyncio
async def test_handle_goal_request_auto_approve_cannot_be_overridden_by_llm(monkeypatch, mock_llm_router, mock_memory):
    monkeypatch.setattr("conversation_engine.settings.OWNER_AUTO_APPROVE_GOALS", True, raising=False)
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory)
    mock_llm_router.call_llm = AsyncMock(
        return_value='{"goal_title":"t","goal_description":"d","confirmation":"c","needs_approval":true}'
    )
    result = await engine._handle_goal_request("сделай лендинг")
    assert result["create_goal"] is True
    assert result["needs_approval"] is False


@pytest.mark.asyncio
async def test_run_deep_research_returns_report_even_if_registry_marks_verification_failure(mock_llm_router, mock_memory, tmp_path):
    owner_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_state.set_active("проведи глубокое исследование", intent="goal_request")
    registry = MagicMock()
    registry.dispatch = AsyncMock(side_effect=[
        MagicMock(
            success=False,
            error="verification_failed:quality_judge",
            output="## Executive Summary\nSolid demand found.\n## Sources\n- reddit",
            metadata={
                "executive_summary": "Solid demand found.",
                "data_sources": ["reddit"],
                "report_path": "/tmp/report.md",
            },
        ),
        MagicMock(success=True, output={"score": 8, "approved": True}),
    ])
    engine = ConversationEngine(
        llm_router=mock_llm_router,
        memory=mock_memory,
        owner_task_state=owner_state,
        agent_registry=registry,
    )
    out = await engine._dispatch_action("run_deep_research", {"topic": "digital products"})
    assert "Глубокое исследование готово" in out
    assert "/tmp/report.md" in out


@pytest.mark.asyncio
async def test_process_message_allows_research_choice_then_create(mock_llm_router, mock_memory, tmp_path):
    owner_state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    owner_state.set_active("исследуй нишу", source="telegram", intent="system_action", force=True)
    owner_state.enrich_active(
        research_options_json=json.dumps([
            {"rank": 1, "title": "Prompt Pack", "score": 89, "platform": "gumroad"},
            {"rank": 2, "title": "Printable Planner", "score": 81, "platform": "etsy"},
        ], ensure_ascii=False),
        research_recommended_json=json.dumps({"title": "Prompt Pack", "score": 89, "platform": "gumroad"}, ensure_ascii=False),
    )
    engine = ConversationEngine(llm_router=mock_llm_router, memory=mock_memory, owner_task_state=owner_state)
    out1 = await engine.process_message("2")
    assert "Зафиксировал вариант 2" in out1["response"]
    out2 = await engine.process_message("создавай")
    assert out2["intent"] == "system_action"
    assert out2["actions"][0]["action"] == "run_product_pipeline"
    assert out2["actions"][0]["params"]["topic"] == "Printable Planner"


@pytest.mark.asyncio
async def test_execute_actions_blocks_unknown_action_without_auto_self_improve(mock_llm_router, mock_memory):
    registry = MagicMock()
    registry.dispatch = AsyncMock()
    engine = ConversationEngine(
        llm_router=mock_llm_router,
        memory=mock_memory,
        agent_registry=registry,
    )
    out = await engine._execute_actions([{"action": "totally_unknown_action", "params": {}}])
    assert "недоступно по политике безопасности" in out
    registry.dispatch.assert_not_called()
