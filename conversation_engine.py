"""ConversationEngine — мозг VITO для общения с владельцем.

Тотальный контроль: видит ВСЕ данные системы, может ВЫПОЛНЯТЬ действия.
Двухступенчатый intent detection: rule-based → LLM.
Хранит контекст последних 20 реплик.

Доступ к модулям:
  - llm_router: расходы по моделям, выбор моделей, цены
  - finance: транзакции, P&L, бюджеты, продукты, ROI
  - goal_engine: цели, статусы, статистика
  - agent_registry: 23 агента, dispatch, статусы
  - decision_loop: управление циклом
  - self_healer: ошибки, самолечение
  - self_updater: обновления, бэкапы, откат
  - knowledge_updater: обновление знаний
  - judge_protocol: стратегический анализ ниш
  - memory: ChromaDB + SQLite + pgvector (навыки, паттерны, знания)
"""

import asyncio
import difflib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings
from modules.owner_model import OwnerModel
from modules.owner_preference_model import OwnerPreferenceModel
from modules.conversation_memory import ConversationMemory
from modules.cancel_state import CancelState
from modules.owner_task_state import OwnerTaskState
from modules.autonomy_proposals import AutonomyProposalStore
from modules.conversation_owner_lane import handle_owner_preroute
from modules.status_snapshot import build_status_snapshot, render_status_snapshot
from modules.telegram_command_compiler import compile_owner_message, parse_owner_message_structured
from modules.conversation_deterministic_owner_lane import (
    deterministic_owner_route as _deterministic_owner_route_impl,
    format_deep_research_owner_report as _format_deep_research_owner_report_impl,
    maybe_continue_from_autonomy_proposals as _maybe_continue_from_autonomy_proposals_impl,
    maybe_continue_from_research_state as _maybe_continue_from_research_state_impl,
)
from modules.conversation_action_lane import (
    # action lane
    dispatch_action as _dispatch_action_impl,
    execute_actions as _execute_actions_impl,
    handle_goal_request as _handle_goal_request_impl,
    handle_system_action as _handle_system_action_impl,
)
from modules.conversation_autonomy_action_lane import handle_autonomy_action as _handle_autonomy_action_impl
from modules.conversation_dialogue_lane import (
    handle_conversation as _handle_conversation_impl,
    handle_feedback as _handle_feedback_impl,
)
from modules.conversation_owner_profile_lane import (
    extract_owner_name as _extract_owner_name_impl,
    extract_owner_raw_text as _extract_owner_raw_text_impl,
    is_probable_name_reply as _is_probable_name_reply_impl,
    remember_owner_profile_fact as _remember_owner_profile_fact_impl,
    resolve_owner_name as _resolve_owner_name_impl,
)
from modules.conversation_parse_lane import (
    extract_platform_key as _extract_platform_key_impl,
    extract_platforms as _extract_platforms_impl,
    extract_product_topic as _extract_product_topic_impl,
    extract_research_topic as _extract_research_topic_impl,
    extract_target_title as _extract_target_title_impl,
    format_time_answer as _format_time_answer_impl,
    is_time_query as _is_time_query_impl,
    looks_like_imperative_request as _looks_like_imperative_request_impl,
)
from modules.conversation_question_lane import handle_question as _handle_question_impl
from modules.conversation_legacy_action_lane import dispatch_action_legacy as _dispatch_action_legacy_impl
from modules.conversation_autonomy_lane import (
    allowed_actions as _allowed_actions_impl,
    autonomous_execute as _autonomous_execute_impl,
    get_available_actions as _get_available_actions_impl,
    infer_capability as _infer_capability_impl,
    maybe_quality_gate as _maybe_quality_gate_impl,
    pick_capability_from_memory as _pick_capability_from_memory_impl,
    record_autonomy_learning as _record_autonomy_learning_impl,
)
from modules.conversation_intake_lane import (
    bootstrap_owner_turn as _bootstrap_owner_turn_impl,
    maybe_handle_fast_url_route as _maybe_handle_fast_url_route_impl,
)
from modules.conversation_context_lane import (
    build_operational_memory_context as _build_operational_memory_context_impl,
    format_system_context as _format_system_context_impl,
)
from modules.conversation_context_memory_lane import (
    add_turn as _add_turn_impl,
    extract_json as _extract_json_impl,
    format_context as _format_context_impl,
    load_context_from_memory as _load_context_from_memory_impl,
    owner_task_focus_text as _owner_task_focus_text_impl,
    persist_turn as _persist_turn_impl,
    turn_from_entry as _turn_from_entry_impl,
)
from modules.conversation_quick_lane import (
    quick_agents as _quick_agents_impl,
    quick_answer as _quick_answer_impl,
    quick_balances as _quick_balances_impl,
    quick_calendar as _quick_calendar_impl,
    quick_errors as _quick_errors_impl,
    quick_goals as _quick_goals_impl,
    quick_pnl as _quick_pnl_impl,
    quick_skills as _quick_skills_impl,
    quick_spend as _quick_spend_impl,
    quick_status as _quick_status_impl,
    quick_updates as _quick_updates_impl,
)
from llm_router import LLMRouter, TaskType, MODEL_REGISTRY
from modules.prompt_guard import wrap_untrusted_text

logger = get_logger("conversation_engine", agent="conversation_engine")

VITO_PERSONALITY = (
    "Ты VITO — автономный AI-агент, бизнес-партнёр владельца. "
    "Отвечай на русском, по делу и человеческим языком.\n\n"
    "СТРОГИЕ ПРАВИЛА КОММУНИКАЦИИ:\n"
    "1. По умолчанию отвечай компактно. "
    "Если это запрос на исследование/анализ — давай развернутый ответ со структурой, выводами, оценкой и идеями.\n"
    "2. ТОЛЬКО по теме разговора. Обсуждаем контент → ни слова про финансы/ошибки/агентов. "
    "Обсуждаем расходы → ни слова про тренды/контент.\n"
    "3. НИКОГДА не кидай файловые пути (/home/...). Покажи текст прямо в сообщении.\n"
    "4. Если создал контент — покажи его текст целиком, не ссылайся на файл.\n"
    "5. Не сбрасывай JSON, логи, сырые данные, ID задач.\n"
    "6. Не требуй искусственно выбирать 'вариант 1/2', если владелец уже дал прямую задачу.\n"
    "7. Продукты/контент — ТОЛЬКО на английском (US/EU рынок).\n"
    "8. Если неуверен (>40%) → спроси перед действием.\n"
    "9. Общайся как человек-партнёр, не как робот с отчётами.\n"
    "10. НИКОГДА не утверждай, что что-то выполнено/опубликовано/загружено, "
    "если это не подтверждено системой.\n"
)

MAX_CONTEXT_TURNS = 20


class Intent(Enum):
    COMMAND = "command"
    APPROVAL = "approval"
    QUESTION = "question"
    GOAL_REQUEST = "goal_request"
    SYSTEM_ACTION = "system_action"
    FEEDBACK = "feedback"
    CONVERSATION = "conversation"


@dataclass
class Turn:
    role: str  # "user" or "assistant"
    text: str
    intent: Optional[Intent] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationEngine:
    def __init__(self, llm_router: LLMRouter, memory, goal_engine=None,
                 finance=None, agent_registry=None, decision_loop=None,
                 self_healer=None, self_updater=None,
                 knowledge_updater=None, judge_protocol=None,
                 code_generator=None, comms=None,
                 conversation_memory: ConversationMemory | None = None, cancel_state: CancelState | None = None,
                 owner_task_state: OwnerTaskState | None = None):
        self.llm_router = llm_router
        self.memory = memory
        self.goal_engine = goal_engine
        self.finance = finance
        self.agent_registry = agent_registry
        self.decision_loop = decision_loop
        self.self_healer = self_healer
        self.self_updater = self_updater
        self.knowledge_updater = knowledge_updater
        self.judge_protocol = judge_protocol
        self.code_generator = code_generator
        self.comms = comms
        self.conversation_memory = conversation_memory
        self.cancel_state = cancel_state
        self.owner_task_state = owner_task_state
        self.owner_model = OwnerModel()
        self.autonomy_proposals = AutonomyProposalStore()
        self._session_id = "default"
        self._defer_owner_actions = False
        self.Intent = Intent
        self.VITO_PERSONALITY = VITO_PERSONALITY
        self._context: list[Turn] = []
        if self.conversation_memory:
            self._load_context_from_memory()
        logger.info("ConversationEngine инициализирован", extra={"event": "init"})

    def set_session(self, session_id: str | None) -> None:
        sid = str(session_id or "default").strip() or "default"
        if sid == self._session_id:
            return
        self._session_id = sid
        self._load_context_from_memory()

    def set_defer_owner_actions(self, enabled: bool) -> None:
        self._defer_owner_actions = bool(enabled)

    async def process_message(self, text: str) -> dict[str, Any]:
        """Обрабатывает сообщение от владельца."""
        self._remember_owner_profile_fact(text)
        try:
            self.owner_model.update_from_interaction(str(text or ""))
        except Exception:
            pass
        if self.cancel_state and self.cancel_state.is_cancelled():
            return {
                "intent": Intent.CONVERSATION.value,
                "response": "Выполнение задач на паузе. Отправь /resume, чтобы продолжить.",
            }
        fast_route = await _maybe_handle_fast_url_route_impl(self, text)
        if fast_route is not None:
            return fast_route
        preroute = await handle_owner_preroute(self, text)
        if preroute is not None:
            return preroute
        # 1. Detect intent + tone
        tones = self._detect_tone(text)
        intent = self._detect_intent_rules(text)
        if intent is None:
            intent = await self._detect_intent_llm(text)

        _bootstrap_owner_turn_impl(self, text, intent, tones)

        # 3. Process by intent
        result = await self._process_by_intent(intent, text)

        # 4. Execute actions if current caller allows blocking execution
        if result.get("actions") and not result.get("needs_confirmation", False) and not self._defer_owner_actions:
            action_results = await self._execute_actions(result["actions"])
            if action_results:
                friendly = self._owner_friendly_action_results(action_results)
                result["response"] = (result.get("response") or "") + "\n\n" + friendly

        # 5. Save assistant turn
        if result.get("response"):
            self._add_turn("assistant", result["response"])

        result["nlu_tones"] = tones
        return result

    def _ensure_owner_task_state(self, text: str, intent_value: str | None) -> None:
        if not self.owner_task_state:
            return
        try:
            active_before = self.owner_task_state.get_active()
            intent_str = str(intent_value or "").strip().lower()
            if intent_str not in {Intent.GOAL_REQUEST.value, Intent.SYSTEM_ACTION.value}:
                return
            saved = self.owner_task_state.set_active(
                text=text,
                source="telegram",
                intent=intent_str,
                force=False,
            )
            if active_before and not saved:
                return
        except Exception:
            return

    @staticmethod
    def _owner_friendly_action_results(text: str) -> str:
        s = str(text or "").strip()
        if not s:
            return "Принял задачу в работу. Дам краткий прогресс и вернусь с результатом."
        low = s.lower()
        noisy = ("task_id", "goal_id", "trace_id", "session_id", "{", "}", "[", "]")
        if any(tok in low for tok in noisy):
            return "Принял задачу в работу. Иду выполнять, вернусь с прогрессом и итогом."
        return s

    async def _deterministic_owner_route(self, text: str) -> dict[str, Any] | None:
        return await _deterministic_owner_route_impl(self, text)

    def _detect_intent_rules(self, text: str) -> Optional[Intent]:
        """Rule-based intent detection (быстрый первый фильтр)."""
        stripped = text.strip()

        if stripped.startswith("/"):
            return Intent.COMMAND

        lower = stripped.lower()
        normalized = self._normalize_for_nlu(stripped)
        # Explicit question markers override goal detection
        if "?" in stripped:
            return Intent.QUESTION
        if lower.startswith(("откуда", "почему", "зачем", "как", "кто", "что", "где", "когда", "какой", "какие", "чем")):
            return Intent.QUESTION

        # Time queries — no LLM needed
        time_words = ("время", "час", "дата", "time", "what time", "date", "сколько время")
        if self._has_keywords(normalized, time_words, fuzzy=True) and len(lower) < 40:
            return Intent.QUESTION
        approval_words = {"да", "нет", "ок", "ok", "yes", "no", "approve", "reject",
                          "отмена", "одобряю", "отклоняю"}
        if lower in approval_words:
            return Intent.APPROVAL

        info_verbs = ("дай", "покажи", "расскажи", "найди", "найти", "проанализируй", "собери")
        info_targets = ("новост", "тренд", "статист", "аналит", "обзор", "отчет", "отчёт", "сводк", "ниши")
        create_targets = ("создай", "опубликуй", "запусти", "загрузи", "сделай продукт", "сделай товар")
        if self._has_keywords(normalized, info_verbs, fuzzy=True) and self._has_keywords(normalized, info_targets, fuzzy=True):
            if not self._has_keywords(normalized, create_targets, fuzzy=True):
                return Intent.QUESTION

        # Goal request keywords (product creation, tasks, publishing)
        goal_keywords = [
            "создай", "сделай", "опубликуй", "напиши", "разработай",
            "запусти продукт", "запусти товар", "продукт", "ebook",
            "найди", "найти", "подбери", "собери", "сформируй",
            "отчет", "отчёт", "тренд", "тренды",
            "create", "make", "publish", "build", "launch", "find", "research",
            "write an", "write a", "design", "generate",
        ]
        if self._has_keywords(normalized, goal_keywords, fuzzy=True):
            return Intent.GOAL_REQUEST

        # System action keywords (internal operations)
        action_keywords = [
            "запусти агент", "останови", "просканируй", "проанализируй",
            "используй", "переключи", "смени модель", "сканируй тренды",
            "проверь ошибки", "сделай бэкап", "откати", "обнови",
        ]
        self_improve_keywords = [
            "исправь", "почини", "доработай", "улучши код", "улучши",
            "самоисправ", "добавь интеграц", "сделай интеграц",
            "добавь поддержку", "добавь навык",
        ]
        learn_service_keywords = [
            "изучи сервис", "изучи платформ", "найди требования", "добавь знания",
            "документац", "официальные требования",
        ]
        if self._has_keywords(normalized, self_improve_keywords, fuzzy=True):
            return Intent.SYSTEM_ACTION
        if self._has_keywords(normalized, learn_service_keywords, fuzzy=True):
            return Intent.SYSTEM_ACTION
        if self._has_keywords(normalized, action_keywords, fuzzy=True):
            return Intent.SYSTEM_ACTION

        return None

    @staticmethod
    def _normalize_for_nlu(text: str) -> str:
        text = (text or "").lower().replace("ё", "е")
        text = re.sub(r"[^a-zа-я0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _has_keywords(self, normalized_text: str, keywords: list[str] | tuple[str, ...], fuzzy: bool = False) -> bool:
        if not normalized_text:
            return False
        tokens = normalized_text.split()
        for raw_kw in keywords:
            kw = self._normalize_for_nlu(str(raw_kw or ""))
            if not kw:
                continue
            if kw in normalized_text:
                return True
            if not fuzzy:
                continue
            if " " in kw:
                continue
            if len(kw) < 4:
                continue
            for token in tokens:
                if len(token) < 4:
                    continue
                if abs(len(token) - len(kw)) > 2:
                    continue
                if difflib.SequenceMatcher(None, token, kw).ratio() >= 0.78:
                    return True
        return False

    def _detect_tone(self, text: str) -> list[str]:
        normalized = self._normalize_for_nlu(text)
        tones: list[str] = []
        frustrated_markers = (
            "не работает", "бесит", "достало", "тупой", "ошибка", "сломал",
            "не можешь", "не делает", "плохо", "ужас", "wtf",
        )
        urgent_markers = ("срочно", "asap", "немедленно", "прямо сейчас", "горит")
        positive_markers = ("спасибо", "отлично", "супер", "класс", "good", "great")
        if self._has_keywords(normalized, frustrated_markers, fuzzy=True):
            tones.append("frustrated")
        if self._has_keywords(normalized, urgent_markers, fuzzy=True):
            tones.append("urgent")
        if self._has_keywords(normalized, positive_markers, fuzzy=True):
            tones.append("positive")
        return tones

    @staticmethod
    def _extract_url(text: str) -> Optional[str]:
        import re
        # Full URL
        m = re.search(r"https?://\S+", text)
        if m:
            return m.group(0).rstrip(".,)")
        # Bare domain (avoid emails)
        m = re.search(r"\b([a-z0-9.-]+\.[a-z]{2,})(/[^\s]*)?\b", text, re.IGNORECASE)
        if m and "@" not in m.group(0):
            return "https://" + m.group(0)
        return None

    async def _detect_intent_llm(self, text: str) -> Intent:
        """LLM-based intent detection через structured Gemini parser."""
        if "?" in text:
            return Intent.QUESTION
        try:
            active = self.owner_task_state.get_active() if self.owner_task_state else {}
        except Exception:
            active = {}
        try:
            parsed = await parse_owner_message_structured(text, active, self.llm_router)
            if parsed:
                detected = {
                    "question": Intent.QUESTION,
                    "goal_request": Intent.GOAL_REQUEST,
                    "system_action": Intent.SYSTEM_ACTION,
                    "feedback": Intent.FEEDBACK,
                    "conversation": Intent.CONVERSATION,
                }.get(str(parsed.get("intent") or "").strip().lower(), Intent.CONVERSATION)
                if detected == Intent.GOAL_REQUEST and ("?" in text):
                    return Intent.QUESTION
                return detected
        except Exception as e:
            logger.debug(f"LLM intent detection failed: {e}", extra={"event": "intent_llm_error"})

        return Intent.CONVERSATION

    async def _process_by_intent(self, intent: Intent, text: str) -> dict[str, Any]:
        if intent == Intent.COMMAND:
            return {"intent": intent.value, "response": None, "pass_through": True}
        if intent == Intent.APPROVAL:
            return {"intent": intent.value, "response": None, "pass_through": True}
        if intent == Intent.QUESTION:
            result = await self._handle_question(text)
        elif intent == Intent.GOAL_REQUEST:
            result = await self._handle_goal_request(text)
        elif intent == Intent.SYSTEM_ACTION:
            result = await self._handle_system_action(text)
        elif intent == Intent.FEEDBACK:
            result = await self._handle_feedback(text)
        else:
            result = await self._handle_conversation(text)
        try:
            if isinstance(result, dict) and isinstance(result.get("response"), str):
                result["response"] = self._guard_response(result["response"])
        except Exception:
            pass
        return result

    # ── Обработчики ──

    async def _handle_question(self, text: str) -> dict[str, Any]:
        """Отвечает на вопрос с полным доступом к системе."""
        return await _handle_question_impl(self, text)

    def _remember_owner_profile_fact(self, text: str) -> None:
        _remember_owner_profile_fact_impl(self, text)

    @staticmethod
    def _extract_owner_raw_text(text: str) -> str:
        return _extract_owner_raw_text_impl(text)

    def _is_probable_name_reply(self, text: str) -> bool:
        return _is_probable_name_reply_impl(self, text)

    def _resolve_owner_name(self) -> str:
        return _resolve_owner_name_impl(self)

    @staticmethod
    def _extract_owner_name(text: str) -> str:
        return _extract_owner_name_impl(text)

    async def _quick_gumroad_analytics(self) -> str:
        if not self.agent_registry:
            return ""
        try:
            result = await self.agent_registry.dispatch("sales_check", platform="gumroad")
        except Exception:
            return ""
        if not result or not getattr(result, "success", False):
            return ""
        data = getattr(result, "output", {}) or {}
        gm = data.get("gumroad", data)
        if not isinstance(gm, dict):
            return ""
        if gm.get("error"):
            return f"Gumroad: доступ есть, но аналитика вернула ошибку: {gm.get('error')}"
        sales = int(gm.get("sales", 0) or 0)
        revenue = float(gm.get("revenue", 0.0) or 0.0)
        products = int(gm.get("products_count", 0) or 0)
        return (
            "Gumroad (live):\n"
            f"- Продажи: {sales}\n"
            f"- Выручка: ${revenue:.2f}\n"
            f"- Продуктов: {products}"
        )

    async def _handle_system_action(self, text: str) -> dict[str, Any]:
        """Выполняет системное действие по запросу владельца."""
        return await _handle_system_action_impl(self, text)

    async def _handle_goal_request(self, text: str) -> dict[str, Any]:
        """Владелец просит что-то сделать → VITO предлагает план → ждёт одобрения."""
        return await _handle_goal_request_impl(self, text)

    async def _handle_feedback(self, text: str) -> dict[str, Any]:
        return await _handle_feedback_impl(self, text)

    async def _handle_conversation(self, text: str) -> dict[str, Any]:
        return await _handle_conversation_impl(self, text)

    def _guard_response(self, response: Optional[str]) -> Optional[str]:
        """Prevent unverified completion claims in free-form responses."""
        if not response:
            return response
        lower = response.lower()
        risky_phrases = [
            "готов и загружен", "готов и опубликован", "опубликован", "загружен",
            "создан и загружен", "создан и опубликован", "я загрузил", "я опубликовал",
            "already uploaded", "already published", "is live", "published on",
        ]
        if any(p in lower for p in risky_phrases):
            try:
                from modules.execution_facts import ExecutionFacts
                facts = ExecutionFacts()
                if not facts.recent_exists(
                    actions=["publisher_agent:publish", "browser_agent:form_fill", "ecommerce_agent:listing_create", "platform:publish"],
                    hours=24,
                ):
                    return "Это было предложение, а не факт выполнения. Если хочешь, запущу это сейчас."
            except Exception:
                return "Это было предложение, а не факт выполнения. Если хочешь, запущу это сейчас."
        return response

    # ── Исполнение действий ──

    async def _execute_actions(self, actions: list[dict]) -> str:
        """Выполняет действия, запрошенные LLM."""
        return await _execute_actions_impl(self, actions)

    async def _dispatch_action(self, action: str, params: dict) -> str:
        return await _dispatch_action_impl(self, action, params)

    async def _dispatch_action_legacy(self, action: str, params: dict) -> str:
        return await _dispatch_action_legacy_impl(self, action, params)


    def _get_available_actions(self) -> str:
        return _get_available_actions_impl(self)

    def _allowed_actions(self) -> set[str]:
        return _allowed_actions_impl(self)

    async def _autonomous_execute(self, request: str) -> str:
        return await _autonomous_execute_impl(self, request)

    def _infer_capability(self, request: str) -> str:
        return _infer_capability_impl(self, request)

    def _pick_capability_from_memory(self, request: str) -> str:
        return _pick_capability_from_memory_impl(self, request)

    async def _maybe_quality_gate(self, capability: str, request: str, output_text: str) -> str:
        return await _maybe_quality_gate_impl(self, capability, request, output_text)

    def _record_autonomy_learning(
        self,
        request: str,
        capability: str,
        success: bool,
        attempts: list[str],
        result_text: str,
    ) -> None:
        return _record_autonomy_learning_impl(self, request, capability, success, attempts, result_text)

    def _record_autonomy_learning(
        self,
        request: str,
        capability: str,
        success: bool,
        attempts: list[str],
        result_text: str,
    ) -> None:
        """Persist autonomous execution lessons for future tasks."""
        mm = self.memory
        if mm is None:
            return
        skill_name = f"autonomy:{capability}"
        try:
            mm.save_skill(
                name=skill_name,
                description=f"Autonomous loop for '{request[:80]}'",
                agent="conversation_engine",
                task_type=capability,
                method={
                    "request": request[:240],
                    "attempts": attempts[:10],
                    "success": bool(success),
                },
            )
            mm.update_skill_success(skill_name, success=bool(success))
            mm.update_skill_last_result(skill_name, str(result_text or "")[:500])
        except Exception:
            pass
        try:
            if success:
                mm.save_pattern(
                    category="autonomy_success",
                    key=f"{capability}:{hash(request) % 100000}",
                    value=" | ".join(attempts[:8]),
                    confidence=0.85,
                )
            else:
                mm.save_pattern(
                    category="anti_pattern",
                    key=f"autonomy_fail:{capability}:{hash(request) % 100000}",
                    value=" | ".join(attempts[:8]),
                    confidence=0.95,
                )
                mm.log_error(
                    module="conversation_engine",
                    error_type="autonomous_execute_failed",
                    message=f"{capability}: {request[:180]}",
                    resolution="auto_learn_retry_scheduled",
                )
        except Exception:
            pass

    @staticmethod
    def _extract_research_topic(text: str) -> str:
        return _extract_research_topic_impl(text)

    @staticmethod
    def _extract_product_topic(text: str) -> str:
        return _extract_product_topic_impl(text)

    @staticmethod
    def _extract_platforms(text: str) -> list[str]:
        return _extract_platforms_impl(text)

    @staticmethod
    def _is_time_query(lower: str) -> bool:
        return _is_time_query_impl(lower)

    @staticmethod
    def _format_time_answer() -> str:
        return _format_time_answer_impl()

    def _quick_answer(self, text: str, lower: str) -> str:
        return _quick_answer_impl(self, text, lower)

    def _build_operational_memory_context(self, text: str, include_errors: bool = True) -> str:
        return _build_operational_memory_context_impl(self, text, include_errors=include_errors)

    @staticmethod
    def _extract_target_title(text: str) -> str:
        return _extract_target_title_impl(text)

    @staticmethod
    def _extract_platform_key(text: str) -> str:
        return _extract_platform_key_impl(text)

    @staticmethod
    def _looks_like_imperative_request(text: str) -> bool:
        return _looks_like_imperative_request_impl(text)

    def _quick_status(self) -> str:
        return _quick_status_impl(self)

    @staticmethod
    @staticmethod
    def _format_deep_research_owner_report(
        *,
        topic: str,
        summary: str,
        score: int,
        verdict: str,
        sources: list[str],
        report_path: str = "",
        top_ideas: list[dict[str, Any]] | None = None,
        recommended_product: dict[str, Any] | None = None,
    ) -> str:
        return _format_deep_research_owner_report_impl(
            topic=topic,
            summary=summary,
            score=score,
            verdict=verdict,
            sources=sources,
            report_path=report_path,
            top_ideas=top_ideas,
            recommended_product=recommended_product,
        )

    def _maybe_continue_from_research_state(self, text: str) -> dict[str, Any] | None:
        return _maybe_continue_from_research_state_impl(self, text)

    def _maybe_continue_from_autonomy_proposals(self, text: str) -> dict[str, Any] | None:
        return _maybe_continue_from_autonomy_proposals_impl(self, text)

    def _quick_spend(self) -> str:
        return _quick_spend_impl(self)

    def _quick_pnl(self) -> str:
        return _quick_pnl_impl(self)

    def _quick_balances(self) -> str:
        return _quick_balances_impl(self)

    def _quick_goals(self) -> str:
        return _quick_goals_impl(self)

    def _quick_agents(self) -> str:
        return _quick_agents_impl(self)

    def _quick_errors(self) -> str:
        return _quick_errors_impl(self)

    def _quick_calendar(self) -> str:
        return _quick_calendar_impl(self)

    def _quick_skills(self) -> str:
        return _quick_skills_impl(self)

    def _quick_updates(self) -> str:
        return _quick_updates_impl(self)

    # ── Полное состояние системы ──

    def _format_system_context(self) -> str:
        return _format_system_context_impl(self)

    # ── Утилиты ──

    def _extract_json(self, text: str) -> Optional[dict]:
        return _extract_json_impl(text)

    def _add_turn(self, role: str, text: str, intent: Optional[Intent] = None) -> None:
        _add_turn_impl(self, role, text, intent)

    def _format_context(self) -> str:
        return _format_context_impl(self)

    def _owner_task_focus_text(self) -> str:
        return _owner_task_focus_text_impl(self)

    def get_context(self) -> list[dict]:
        return [
            {
                "role": t.role,
                "text": t.text[:100],
                "intent": t.intent.value if t.intent else None,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in self._context
        ]

    def clear_context(self) -> None:
        self._context.clear()
        if self.conversation_memory:
            try:
                self.conversation_memory.clear(session_id=self._session_id)
            except Exception:
                pass

    def _load_context_from_memory(self) -> None:
        _load_context_from_memory_impl(self)

    def _turn_from_entry(self, entry: dict) -> Turn | None:
        return _turn_from_entry_impl(entry)

    def _persist_turn(self, turn: Turn) -> None:
        _persist_turn_impl(self, turn)
