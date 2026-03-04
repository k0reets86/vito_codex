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
from modules.owner_preference_model import OwnerPreferenceModel
from modules.conversation_memory import ConversationMemory
from modules.cancel_state import CancelState
from modules.owner_task_state import OwnerTaskState
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
        self._session_id = "default"
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

    async def process_message(self, text: str) -> dict[str, Any]:
        """Обрабатывает сообщение от владельца."""
        owner_task_preserved = False
        self._remember_owner_profile_fact(text)
        if self.cancel_state and self.cancel_state.is_cancelled():
            return {
                "intent": Intent.CONVERSATION.value,
                "response": "Выполнение задач на паузе. Отправь /resume, чтобы продолжить.",
            }
        # Fast path: browser/web fetch without LLM
        url = self._extract_url(text)
        if url and self.agent_registry and settings.BROWSER_DEFAULT_ON_URL:
            # Prefer real browser for JS-heavy sites
            try:
                lower = text.lower()
                if any(k in lower for k in ("скрин", "снимок", "screenshot", "screen")):
                    task_type = "screenshot"
                    path = f"/tmp/vito_browse_{int(time.time())}.png"
                    result = await self.agent_registry.dispatch(task_type, url=url, path=path)
                    if result and result.success:
                        return {
                            "response": f"Открыл страницу. Скриншот готов.\n📎 {result.output.get('path') if isinstance(result.output, dict) and result.output.get('path') else path}",
                            "intent": Intent.QUESTION.value,
                        }
                if any(k in lower for k in ("текст", "прочитай", "extract", "вытащи", "что написано")):
                    task_type = "web_scrape"
                    result = await self.agent_registry.dispatch(task_type, url=url, selector="body")
                    if result and result.success:
                        return {
                            "response": f"Текст со страницы:\n{str(result.output)[:3500]}",
                            "intent": Intent.QUESTION.value,
                        }
                # default: quick browse (title + status)
                result = await self.agent_registry.dispatch("browse", url=url)
                if result and result.success:
                    out = result.output or {}
                    title = out.get("title", "")
                    status = out.get("status", "")
                    return {"response": f"Страница открыта. {title} (HTTP {status})", "intent": Intent.QUESTION.value}
            except Exception:
                pass

        # Fallback: fetch URL without LLM (free web fetch)
        if "http://" in text or "https://" in text:
            try:
                import re
                from modules.web_fetch import fetch_url
                m = re.search(r"https?://\S+", text)
                if m:
                    url = m.group(0).rstrip(".,)")
                    data = fetch_url(url)
                    response = f"URL: {url}\nTitle: {data.get('title','')}\n\n{data.get('text','')}"
                    return {"response": response, "intent": Intent.QUESTION.value}
            except Exception:
                pass
        deterministic = await self._deterministic_owner_route(text)
        if deterministic is not None:
            try:
                self._add_turn("user", text, Intent.SYSTEM_ACTION if deterministic.get("intent") == Intent.SYSTEM_ACTION.value else Intent.QUESTION)
                if deterministic.get("response"):
                    self._add_turn("assistant", deterministic["response"])
            except Exception:
                pass
            deterministic["nlu_tones"] = self._detect_tone(text)
            return deterministic
        # 1. Detect intent + tone
        tones = self._detect_tone(text)
        intent = self._detect_intent_rules(text)
        if intent is None:
            intent = await self._detect_intent_llm(text)

        # 2. Save user turn
        self._add_turn("user", text, intent)
        if self.owner_task_state and intent in (Intent.GOAL_REQUEST, Intent.SYSTEM_ACTION):
            try:
                active_before = self.owner_task_state.get_active()
                saved = self.owner_task_state.set_active(text=text, source="telegram", intent=intent.value, force=False)
                owner_task_preserved = bool(active_before and not saved)
            except Exception:
                pass

        # 2.5. Сохраняем важные запросы владельца в долгосрочную память
        if intent in (Intent.GOAL_REQUEST, Intent.QUESTION, Intent.SYSTEM_ACTION) and self.memory:
            try:
                self.memory.store_knowledge(
                    doc_id=f"user_msg_{int(time.time())}",
                    text=f"Владелец: {text}",
                    metadata={"type": "user_request", "intent": intent.value, "tones": tones},
                )
            except Exception:
                pass

        # 3. Process by intent
        result = await self._process_by_intent(intent, text)

        # 4. Execute actions if LLM requested them
        if result.get("actions") and not result.get("needs_confirmation", False):
            action_results = await self._execute_actions(result["actions"])
            if action_results:
                friendly = self._owner_friendly_action_results(action_results)
                result["response"] = (result.get("response") or "") + "\n\n" + friendly

        # 5. Save assistant turn
        if result.get("response"):
            self._add_turn("assistant", result["response"])

        result["nlu_tones"] = tones
        return result

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
        """Deterministic command routing for high-priority owner intents.

        This path avoids LLM ambiguity for operational requests and returns
        verifiable execution summaries when possible.
        """
        if str(text or "").strip().startswith("/"):
            return None
        normalized = self._normalize_for_nlu(text)

        status_kw = ("статус", "status", "как дела", "что по задач", "активные задач", "progress", "прогресс")
        if self._has_keywords(normalized, status_kw, fuzzy=True):
            return {"intent": Intent.QUESTION.value, "response": self._quick_status()}

        net_kw = ("интернет", "network", "сеть", "доступ к интернет", "online")
        check_kw = ("проверь", "check", "есть ли", "доступ")
        if self._has_keywords(normalized, net_kw, fuzzy=True) and self._has_keywords(normalized, check_kw, fuzzy=True):
            try:
                from modules.network_utils import basic_net_report
                rep = basic_net_report(["api.telegram.org", "gumroad.com", "api.gumroad.com", "google.com"])
                dns = rep.get("dns", {})
                lines = ["Проверка сети:"]
                for host, ok in dns.items():
                    lines.append(f"- {host}: {'ok' if ok else 'fail'}")
                lines.append(f"- общий статус: {'online' if rep.get('ok') else 'offline'}")
                if rep.get("seccomp"):
                    lines.append(f"- причина блокировки: {rep.get('seccomp')}")
                return {"intent": Intent.QUESTION.value, "response": "\n".join(lines)}
            except Exception:
                return None

        trend_request = self._has_keywords(normalized, ("тренд", "trends", "trend", "ниш", "niche"), fuzzy=True)
        trend_verb = self._has_keywords(normalized, ("найд", "скан", "проскан", "проанализ", "подбери", "research"), fuzzy=True)
        deep_request = self._has_keywords(normalized, ("глубок", "deep", "исследован", "research"), fuzzy=True)
        if deep_request and self._has_keywords(normalized, ("анализ", "исслед", "research", "разбор"), fuzzy=True):
            topic = self._extract_research_topic(text)
            actions = [{"action": "run_deep_research", "params": {"topic": topic}}]
            out = await self._execute_actions(actions)
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": f"Запускаю глубокое исследование по теме: {topic}.\n{out or 'Собираю источники и готовлю детальный отчёт.'}",
                "actions": actions,
                "needs_confirmation": False,
            }
        if trend_request and trend_verb and self.agent_registry:
            actions = [{"action": "scan_trends", "params": {}}]
            out = await self._execute_actions(actions)
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": f"Сканирование трендов запущено.\n{out or 'Запуск принят, формирую результат.'}",
                "actions": actions,
                "needs_confirmation": False,
            }

        analytics_kw = ("аналит", "analytics", "отчет", "отчёт", "report", "dashboard")
        if self._has_keywords(normalized, analytics_kw, fuzzy=True) and self.agent_registry:
            try:
                result = await self.agent_registry.dispatch("analytics", objective=text)
                if result and result.success:
                    return {
                        "intent": Intent.SYSTEM_ACTION.value,
                        "response": f"Команда выполнена: аналитика готова.\n[evidence] analytics output: {str(result.output)[:1200]}",
                    }
            except Exception:
                pass

        etsy_kw = ("etsy", "етси", "этси")
        oauth_kw = ("oauth", "pkce", "подключ", "авториз", "логин", "token", "токен")
        if self._has_keywords(normalized, etsy_kw, fuzzy=True) and self._has_keywords(normalized, oauth_kw, fuzzy=True):
            try:
                from platforms.etsy import EtsyPlatform
                etsy = EtsyPlatform()
                start = await etsy.start_oauth2_pkce()
                await etsy.close()
                auth_url = start.get("auth_url", "")
                redir = start.get("redirect_uri", "")
                if auth_url:
                    return {
                        "intent": Intent.SYSTEM_ACTION.value,
                        "response": (
                            "Etsy OAuth подготовлен.\n"
                            f"- auth_url: {auth_url}\n"
                            f"- redirect_uri: {redir}\n"
                            "После авторизации пришли мне code из callback."
                        ),
                    }
            except Exception:
                pass

        gumroad_kw = ("gumroad", "гумроад", "гамроад")
        sales_kw = ("стат", "statistics", "analytics", "продаж", "revenue", "выручк", "доход")
        if self._has_keywords(normalized, gumroad_kw, fuzzy=True) and self._has_keywords(normalized, sales_kw, fuzzy=True):
            live = await self._quick_gumroad_analytics()
            if live:
                return {"intent": Intent.QUESTION.value, "response": live}

        priority_kw = ("приоритет", "priority")
        goal_kw = ("цели", "goal")
        if self._has_keywords(normalized, priority_kw, fuzzy=True) and self._has_keywords(normalized, goal_kw, fuzzy=True):
            m = re.search(r"\b([a-z0-9]{6,40})\b", normalized)
            p = re.search(r"\b(low|medium|high|critical|низк\w*|средн\w*|высок\w*|критич\w*)\b", normalized)
            goal_id = m.group(1) if m else ""
            raw_priority = p.group(1).lower() if p else "high"
            if raw_priority.startswith("low") or raw_priority.startswith("низк"):
                priority = "LOW"
            elif raw_priority.startswith("med") or raw_priority.startswith("сред"):
                priority = "MEDIUM"
            elif raw_priority.startswith("crit") or raw_priority.startswith("крит"):
                priority = "CRITICAL"
            else:
                priority = "HIGH"
            if goal_id:
                out = await self._execute_actions([{"action": "change_priority", "params": {"goal_id": goal_id, "priority": priority}}])
                return {
                    "intent": Intent.SYSTEM_ACTION.value,
                    "response": f"Изменение приоритета отправлено.\n{out or 'Запрос принят в работу.'}",
                    "actions": [{"action": "change_priority", "params": {"goal_id": goal_id, "priority": priority}}],
                    "needs_confirmation": False,
                }

        err_kw = ("ошибк", "error", "exceptions", "исключен")
        check_kw = ("проверь", "check", "статус", "summary", "сводк")
        system_kw = ("систем", "system")
        if self._has_keywords(normalized, err_kw, fuzzy=True) and (
            self._has_keywords(normalized, check_kw, fuzzy=True)
            or self._has_keywords(normalized, system_kw, fuzzy=True)
        ):
            if self.self_healer and hasattr(self.self_healer, "get_error_stats"):
                try:
                    stats = self.self_healer.get_error_stats()
                    total = int(stats.get("total", 0) or 0)
                    resolved = int(stats.get("resolved", 0) or 0)
                    unresolved = int(stats.get("unresolved", 0) or 0)
                    return {
                        "intent": Intent.QUESTION.value,
                        "response": (
                            "Ошибки системы:\n"
                            f"- total: {total}\n"
                            f"- resolved: {resolved}\n"
                            f"- unresolved: {unresolved}"
                        ),
                    }
                except Exception:
                    pass
            return {
                "intent": Intent.QUESTION.value,
                "response": "Ошибки системы: модуль self_healer недоступен.",
            }

        return None

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
        """LLM-based intent detection через Haiku (~50 токенов)."""
        if "?" in text:
            return Intent.QUESTION
        prompt = (
            f"Определи intent сообщения пользователя. Ответь ОДНИМ словом:\n"
            f"QUESTION — вопрос о системе, данных, статусе, расходах, трендах\n"
            f"GOAL_REQUEST — просьба создать цель или задачу\n"
            f"SYSTEM_ACTION — команда: запустить агента, сканировать, изменить настройки\n"
            f"FEEDBACK — отзыв, благодарность, критика\n"
            f"CONVERSATION — свободный разговор, приветствие\n\n"
            f'Сообщение: "{text}"\n\n'
            f"Intent:"
        )

        try:
            response = await self.llm_router.call_llm(
                task_type=TaskType.ROUTINE,
                prompt=prompt,
                estimated_tokens=50,
            )
            if response:
                intent_str = response.strip().upper().replace(" ", "_")
                intent_map = {
                    "QUESTION": Intent.QUESTION,
                    "GOAL_REQUEST": Intent.GOAL_REQUEST,
                    "SYSTEM_ACTION": Intent.SYSTEM_ACTION,
                    "FEEDBACK": Intent.FEEDBACK,
                    "CONVERSATION": Intent.CONVERSATION,
                }
                detected = intent_map.get(intent_str, Intent.CONVERSATION)
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
        lower = text.strip().lower()
        normalized = self._normalize_for_nlu(text)
        if self._has_keywords(normalized, ("как меня зовут", "мое имя", "моё имя", "забыл мое имя", "my name"), fuzzy=True):
            owner_name = self._resolve_owner_name()
            if owner_name:
                return {
                    "intent": Intent.QUESTION.value,
                    "response": f"Тебя зовут {owner_name}.",
                }
            return {
                "intent": Intent.QUESTION.value,
                "response": "Пока не вижу в памяти твоего имени. Напиши: 'меня зовут ...', и я запомню.",
            }
        # Direct answer for "source of claim" questions to avoid hallucinations
        if any(w in lower for w in ("откуда", "почему ты", "почему вы", "ты писал", "ты написал", "ты сказала", "ты говорил")):
            return {
                "intent": Intent.QUESTION.value,
                "response": "У меня нет подтверждённых данных о публикации/создании. Это было ошибочное сообщение. Исправляю: без факта выполнения больше так не пишу.",
            }
        gumroad_kw = ("gumroad", "гумроад", "гамроад")
        analytics_kw = ("стат", "statistics", "analytics", "продаж", "revenue", "выручк", "доход")
        if self._has_keywords(normalized, gumroad_kw, fuzzy=True) and self._has_keywords(normalized, analytics_kw, fuzzy=True):
            live = await self._quick_gumroad_analytics()
            if live:
                return {
                    "intent": Intent.QUESTION.value,
                    "response": live,
                }
        if self._is_time_query(lower):
            return {
                "intent": Intent.QUESTION.value,
                "response": self._format_time_answer(),
            }
        quick = self._quick_answer(lower)
        if quick:
            return {
                "intent": Intent.QUESTION.value,
                "response": quick,
            }

        context_from_memory = ""
        if self.memory:
            try:
                similar = self.memory.search_knowledge(text, n_results=3)
                if similar:
                    context_from_memory = "\n\nИз памяти VITO:\n" + "\n".join(
                        f"- {doc['text'][:200]}" for doc in similar
                    )
            except Exception:
                pass
            try:
                skills = self.memory.search_skills(text, limit=3)
                if skills:
                    context_from_memory += "\n\nНавыки VITO:\n" + "\n".join(
                        f"- {s['name']}: {s['description'][:150]} (успех: {s.get('success_count', 0)})"
                        for s in skills
                    )
            except Exception:
                pass
        try:
            prefs = OwnerPreferenceModel().list_preferences(limit=5)
            if prefs:
                pref_lines = "\n".join(f"- {p.get('pref_key')}: {p.get('value')}" for p in prefs)
                context_from_memory += f"\n\nПредпочтения владельца:\n{pref_lines}"
        except Exception:
            pass

        system_context = self._format_system_context()
        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== ПОЛНОЕ СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n"
            f"=== КОНЕЦ СОСТОЯНИЯ ===\n\n"
            f"История разговора:\n{self._format_context()}\n\n"
            f"{context_from_memory}\n\n"
            f"Вопрос владельца: {wrap_untrusted_text(text)}\n\n"
            f"ВАЖНО: отвечай с КОНКРЕТНЫМИ цифрами и данными из системы выше. "
            f"Не говори что данных нет — они есть в состоянии системы."
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=800,
        )

        return {
            "intent": Intent.QUESTION.value,
            "response": self._guard_response(response) if response else "Не удалось получить ответ. Попробуй переформулировать.",
        }

    def _remember_owner_profile_fact(self, text: str) -> None:
        """Best-effort extraction of stable owner profile facts from natural speech."""
        source_text = self._extract_owner_raw_text(text)
        owner_name = self._extract_owner_name(source_text)
        if not owner_name and self._is_probable_name_reply(source_text):
            owner_name = source_text.title()
        if not owner_name:
            return
        try:
            OwnerPreferenceModel().set_preference(
                key="owner_name",
                value={"name": owner_name},
                source="owner",
                confidence=1.0,
                notes="extracted_from_chat",
            )
        except Exception:
            pass

    @staticmethod
    def _extract_owner_raw_text(text: str) -> str:
        raw = str(text or "").strip()
        if "[REPLY_CONTEXT]" not in raw:
            return raw
        m = re.search(r"owner_reply=(.*)", raw)
        if m:
            return str(m.group(1) or "").strip()
        return raw

    def _is_probable_name_reply(self, text: str) -> bool:
        raw = str(text or "").strip()
        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\\-]{2,40}", raw):
            return False
        if raw.lower() in {"да", "нет", "ок", "yes", "no", "approve", "reject"}:
            return False
        prompts = ("как тебя зовут", "как вас зовут", "твое имя", "твоё имя", "ваше имя", "your name")
        for turn in reversed(self._context[-6:]):
            if turn.role != "assistant":
                continue
            if self._has_keywords(self._normalize_for_nlu(turn.text), prompts, fuzzy=True):
                return True
        return False

    def _resolve_owner_name(self) -> str:
        try:
            pref = OwnerPreferenceModel().get_preference("owner_name")
            if pref and isinstance(pref.get("value"), dict):
                name = str(pref["value"].get("name", "")).strip()
                if name:
                    return name
        except Exception:
            pass
        for turn in reversed(self._context):
            if turn.role != "user":
                continue
            guessed = self._extract_owner_name(turn.text)
            if guessed:
                return guessed
        return ""

    @staticmethod
    def _extract_owner_name(text: str) -> str:
        raw = ConversationEngine._extract_owner_raw_text(text)
        if not raw:
            return ""
        patterns = [
            r"\bменя\s+зовут\s+([A-Za-zА-Яа-яЁё\-]{2,40})",
            r"\bmy\s+name\s+is\s+([A-Za-zА-Яа-яЁё\-]{2,40})",
            r"\bi\s*am\s+([A-Za-zА-Яа-яЁё\-]{2,40})",
        ]
        for pat in patterns:
            m = re.search(pat, raw, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip().title()
        return ""

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
        system_context = self._format_system_context()
        available_actions = self._get_available_actions()
        conversation_ctx = self._format_context()
        owner_focus = self._owner_task_focus_text()

        # Fast path for explicit self-improve requests
        lower = text.lower()
        self_improve_keywords = [
            "исправь", "почини", "доработай", "улучши код", "улучши",
            "самоисправ", "добавь интеграц", "сделай интеграц",
            "добавь поддержку", "добавь навык",
        ]
        if any(kw in lower for kw in self_improve_keywords):
            require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": (
                    "Запускаю self-improve пайплайн (анализ -> код -> тесты)."
                    if not require_confirm
                    else "Подтверждаешь запуск self-improve пайплайна (анализ -> код -> тесты)? Ответь: да/нет."
                ),
                "actions": [{"action": "self_improve", "params": {"request": text}}],
                "needs_confirmation": require_confirm,
            }
        trend_request = any(kw in lower for kw in ("тренд", "trends", "trend", "ниш", "niche"))
        trend_verb = any(kw in lower for kw in ("найд", "скан", "проскан", "проанализ", "подбери", "research"))
        if any(kw in lower for kw in ("глубок", "deep research", "deep", "глубокое исслед", "детальный анализ")):
            topic = self._extract_research_topic(text)
            actions = [{"action": "run_deep_research", "params": {"topic": topic}}]
            out = await self._execute_actions(actions)
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": f"Запускаю глубокое исследование: {topic}.\n{out or 'Собираю данные и источники.'}",
                "actions": actions,
                "needs_confirmation": False,
            }
        if any(kw in lower for kw in ("под ключ", "turnkey", "сделай товар", "создай товар", "запусти продукт", "product pipeline")):
            topic = self._extract_product_topic(text)
            platforms = self._extract_platforms(text)
            require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": (
                    f"Собираю продукт под ключ: {topic} (платформы: {', '.join(platforms)}). "
                    "Сделаю исследование, SEO, контент, юридическую проверку, публикационный пакет и SMM-план."
                    if not require_confirm
                    else f"Подтверждаешь запуск product pipeline под ключ: {topic} (платформы: {', '.join(platforms)})? да/нет"
                ),
                "actions": [{"action": "run_product_pipeline", "params": {"topic": topic, "platforms": platforms, "auto_publish": False}}],
                "needs_confirmation": require_confirm,
            }
        if any(kw in lower for kw in ("прокач", "улучши себя", "самообуч", "саморазвит", "обнови навыки", "improvement cycle")):
            require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": (
                    "Запускаю цикл прокачки: backup -> HR аудит -> research -> self-improve -> безопасная проверка."
                    if not require_confirm
                    else "Подтверждаешь запуск цикла прокачки (backup -> HR -> research -> self-improve)? да/нет"
                ),
                "actions": [{"action": "run_improvement_cycle", "params": {"request": text}}],
                "needs_confirmation": require_confirm,
            }
        if trend_request and trend_verb:
            actions = [{"action": "scan_trends", "params": {}}]
            out = await self._execute_actions(actions)
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": f"Запустил скан трендов.\n{out or 'Результат формируется, скоро пришлю сводку.'}",
                "actions": actions,
                "needs_confirmation": False,
            }
        if any(kw in lower for kw in ["изучи сервис", "изучи платформ", "добавь знания", "найди требования"]):
            # crude extraction of service name from text
            service = text.replace("изучи", "").replace("платформу", "").replace("сервис", "").strip()
            require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": (
                    f"Запускаю изучение сервиса '{service or 'unknown'}' и обновление базы знаний."
                    if not require_confirm
                    else f"Подтверждаешь изучение сервиса '{service or 'unknown'}' и обновление базы знаний? Ответь: да/нет."
                ),
                "actions": [{"action": "learn_service", "params": {"service": service}}],
                "needs_confirmation": require_confirm,
            }
        if bool(getattr(settings, "AUTONOMY_AUTO_EXECUTE_REQUESTS", False)):
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": "Принял задачу. Выполняю автономно: сначала попробую существующими навыками, при необходимости доучусь и повторю.",
                "actions": [{"action": "autonomous_execute", "params": {"request": text}}],
                "needs_confirmation": False,
            }

        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
            f"{owner_focus}\n\n"
            f"История разговора:\n{conversation_ctx}\n\n"
            f"Доступные действия:\n{available_actions}\n\n"
            f"Владелец просит: \"{wrap_untrusted_text(text)}\"\n\n"
            f"Определи какие действия нужно выполнить и дай подтверждение.\n"
            f"Ответь в JSON:\n"
            f'{{"response": "текст ответа владельцу", '
            f'"actions": [{{"action": "имя_действия", "params": {{...}}}}]}}\n\n'
            f"Если действие не нужно — actions: []"
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=500,
        )

        actions = []
        reply = f"Принял: {text[:80]}"

        if response:
            try:
                parsed = self._extract_json(response)
                if parsed:
                    reply = parsed.get("response", reply)
                    actions = parsed.get("actions", [])
            except Exception:
                reply = response
        if "вот план" in str(reply).lower() and "думаешь" in str(reply).lower():
            reply = "Принял. Запускаю выполнение и вернусь с результатом."
        risky_actions = {"apply_code_change"}
        needs_confirmation = any(
            str(a.get("action", "")).strip() in risky_actions
            for a in actions
            if isinstance(a, dict)
        )
        if actions and needs_confirmation:
            reply = f"{reply}\nПодтверди выполнение: да/нет."

        return {
            "intent": Intent.SYSTEM_ACTION.value,
            "response": reply,
            "actions": actions,
            "needs_confirmation": needs_confirmation,
        }

    async def _handle_goal_request(self, text: str) -> dict[str, Any]:
        """Владелец просит что-то сделать → VITO предлагает план → ждёт одобрения.

        Approval workflow:
        1. Владелец описывает задачу
        2. VITO формирует план и оценку
        3. Отправляет на одобрение: "Вот план. Делаем? ✅/❌"
        4. После одобрения — выполняет
        5. По завершении — показывает результат + ссылку

        "Не уверен — спроси" rule: если задача неясна или есть несколько
        вариантов — VITO уточняет у владельца перед началом.
        """
        system_context = self._format_system_context()
        conversation_ctx = self._format_context()
        owner_focus = self._owner_task_focus_text()

        # Проверяем навыки и знания для этой задачи (no extra LLM call)
        skills_context = ""
        owner_prefs = ""
        if self.memory:
            try:
                skills = self.memory.search_skills(text, limit=3)
                if skills:
                    skills_context = "\nНавыки: " + ", ".join(s['name'] for s in skills)
            except Exception:
                pass
            # Check owner preferences from memory
            try:
                prefs = self.memory.search_knowledge("owner preference", n_results=3)
                if prefs:
                    owner_prefs = "\nПредпочтения владельца:\n" + "\n".join(
                        f"- {p['text'][:150]}" for p in prefs
                    )
            except Exception:
                pass
            # Explicit owner preferences (structured model)
            try:
                model = OwnerPreferenceModel()
                pref_rows = model.list_preferences(limit=5)
                if pref_rows:
                    lines = []
                    keys = []
                    for pr in pref_rows:
                        conf = float(pr.get("confidence", 0))
                        val = pr.get("value")
                        key = pr.get("pref_key")
                        keys.append(key)
                        lines.append(f"- {key}: {val} (conf={conf:.2f})")
                    owner_prefs = owner_prefs + "\n" + "\n".join(lines) if owner_prefs else "\nПредпочтения владельца:\n" + "\n".join(lines)
                    try:
                        from modules.data_lake import DataLake
                        DataLake().record(
                            agent="conversation_engine",
                            task_type="owner_prefs_used",
                            status="success",
                            output={"keys": keys},
                            source="system",
                        )
                    except Exception:
                        pass
            except Exception:
                pass

        auto_approve = bool(getattr(settings, "OWNER_AUTO_APPROVE_GOALS", True))
        approval_hint = (
            "2. Можно начинать сразу и выдать первый результат без дополнительного подтверждения\n"
            if auto_approve
            else "2. НЕ начинай сразу. Сформируй план и предложи на одобрение\n"
        )
        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
            f"{owner_focus}\n\n"
            f"История разговора:\n{conversation_ctx}\n\n"
            f"{skills_context}{owner_prefs}\n\n"
            f"Владелец просит: \"{wrap_untrusted_text(text)}\"\n\n"
            f"ПРАВИЛА:\n"
            f"1. Все продукты/контент — на АНГЛИЙСКОМ (US/CA/EU market)\n"
            f"{approval_hint}"
            f"3. Если что-то неясно — задай вопрос владельцу (на русском)\n"
            f"4. План должен завершаться конкретным результатом: файл, ссылка, публикация\n\n"
            f"Доступные инструменты:\n"
            f"- 23 агента (content_creator, smm_agent, research_agent, browser_agent и др.)\n"
            f"- Платформы: Gumroad, Printful, Twitter\n"
            f"- Генерация изображений: Replicate, BFL, WaveSpeed, DALL-E\n"
            f"- CodeGenerator: может дописать код VITO\n"
            f"- BrowserAgent: может зарегистрироваться на сайтах, заполнять формы\n\n"
            f"Ответь JSON:\n"
            f'{{"goal_title": "краткое название (English)", '
            f'"goal_description": "план 5-7 шагов (English content, but plan itself in Russian for owner)", '
            f'"confirmation": "кратко и по-человечески на русском: принял задачу и начинаю выполнение", '
            f'"needs_approval": {str(not auto_approve).lower()}, '
            f'"estimated_cost_usd": 0.05, '
            f'"priority": "HIGH"}}'
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=600,
        )

        goal_title = text[:100]
        goal_description = text
        confirmation = (
            f"Принял задачу: \"{goal_title}\"\n\nНачинаю выполнение и отправлю полный отчёт."
            if auto_approve
            else f"Принял задачу: \"{goal_title}\"\n\nГотовлю план. Отправлю на одобрение."
        )
        priority = "HIGH"
        needs_approval = not auto_approve
        estimated_cost = 0.05

        if response:
            try:
                data = self._extract_json(response)
                if data:
                    goal_title = data.get("goal_title", goal_title)
                    goal_description = data.get("goal_description", text)
                    confirmation = data.get("confirmation", confirmation)
                    priority = data.get("priority", "HIGH")
                    needs_approval = data.get("needs_approval", not auto_approve)
                    estimated_cost = data.get("estimated_cost_usd", 0.05)
            except Exception:
                pass
        # Owner policy has priority: with auto-approve enabled, LLM cannot force extra approval round.
        if auto_approve:
            needs_approval = False

        # If needs_approval — create goal in WAITING_APPROVAL state
        # The goal will wait for owner's ✅ before execution
        return {
            "intent": Intent.GOAL_REQUEST.value,
            "response": confirmation,
            "create_goal": True,
            "goal_title": goal_title,
            "goal_description": goal_description,
            "goal_priority": priority,
            "needs_approval": needs_approval,
            "estimated_cost_usd": estimated_cost,
        }

    async def _handle_feedback(self, text: str) -> dict[str, Any]:
        if self.memory:
            try:
                self.memory.save_pattern(
                    category="feedback",
                    key=f"fb_{int(time.time())}",
                    value=text[:500],
                    confidence=0.8,
                )
            except Exception:
                pass

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=(
                f"{VITO_PERSONALITY}\n\n"
                f"Владелец оставил отзыв: \"{text}\"\n"
                f"Поблагодари коротко и скажи как учтёшь. 2-3 предложения максимум."
            ),
            estimated_tokens=200,
        )

        return {
            "intent": Intent.FEEDBACK.value,
            "response": response or "Спасибо за обратную связь! Учту.",
        }

    async def _handle_conversation(self, text: str) -> dict[str, Any]:
        # Лёгкий контекст для обычного разговора — без полного дампа системы
        now = datetime.now(timezone.utc)
        light_context = f"Время: {now.strftime('%Y-%m-%d %H:%M UTC')}"
        try:
            daily_spend = self.llm_router.get_daily_spend()
            light_context += f"\nРасходы сегодня: ${daily_spend:.2f} / ${settings.DAILY_LIMIT_USD:.2f}"
        except Exception:
            pass

        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"{light_context}\n\n"
            f"{self._owner_task_focus_text()}\n\n"
            f"История:\n{self._format_context()}\n\n"
            f"Владелец: {text}\n\n"
            f"Ответь коротко и по теме. Не добавляй информацию, о которой не спрашивали."
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=500,
        )

        return {
            "intent": Intent.CONVERSATION.value,
            "response": self._guard_response(response) or "Привет! Я VITO, твой AI-напарник. Чем могу помочь?",
        }

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
        results = []
        allowed = self._allowed_actions()
        for act in actions[:3]:  # max 3 действия за раз
            action_name = act.get("action", "")
            params = act.get("params", {})
            try:
                if action_name not in allowed:
                    results.append(f"Действие '{action_name}' недоступно по политике безопасности.")
                    continue
                if action_name == "apply_code_change":
                    if not self.comms:
                        results.append("Не могу изменить код: канал подтверждения недоступен.")
                        continue
                    target = params.get("file", "")
                    instruction = params.get("instruction", "")
                    approved = await self.comms.request_approval(
                        request_id=f"code_change_{int(time.time())}",
                        message=(
                            "[conversation_engine] Запрос изменения кода.\n"
                            "Подтверди ✅ или отклони ❌.\n"
                            f"Файл: {target}\n"
                            f"Инструкция: {instruction[:300]}"
                        ),
                        timeout_seconds=3600,
                    )
                    if approved is not True:
                        results.append("Изменение кода отменено: подтверждение не получено.")
                        continue
                result = await self._dispatch_action(action_name, params)
                if result:
                    results.append(str(result))
                else:
                    results.append(f"Действие '{action_name}' выполнено.")
            except Exception as e:
                results.append(f"Ошибка при выполнении '{action_name}': {e}")
                logger.warning(f"Action error {action_name}: {e}", extra={"event": "action_error"})
        return "\n".join(results) if results else ""

    async def _dispatch_action(self, action: str, params: dict) -> str:
        """Роутер действий — подключён ко всем модулям."""

        # Агенты
        if action == "dispatch_agent" and self.agent_registry:
            task_type = params.get("task_type", "")
            clean_params = {k: v for k, v in params.items() if k != "task_type"}
            result = await self.agent_registry.dispatch(task_type, **clean_params)
            if result and result.success:
                return f"Агент выполнил: {str(result.output)[:300]}"
            return f"Агент не смог выполнить: {result.error if result else 'нет агента'}"

        if action == "scan_trends" and self.agent_registry:
            result = await self.agent_registry.dispatch("trend_scan", **params)
            return f"Тренды: {str(result.output)[:300]}" if result and result.success else "Сканирование не удалось"

        if action == "scan_reddit" and self.agent_registry:
            result = await self.agent_registry.dispatch("reddit_scan", **params)
            return f"Reddit: {str(result.output)[:300]}" if result and result.success else "Сканирование не удалось"

        # Цели
        if action == "cancel_goal" and self.goal_engine:
            goal_id = params.get("goal_id", "")
            if self.goal_engine.delete_goal(goal_id):
                return f"Цель {goal_id} удалена"
            self.goal_engine.fail_goal(goal_id, "Отменено владельцем")
            return f"Цель {goal_id} отменена (не удалось удалить)"

        if action == "change_priority" and self.goal_engine:
            from goal_engine import GoalPriority
            goal_id = params.get("goal_id", "")
            priority = params.get("priority", "MEDIUM")
            goal = self.goal_engine._goals.get(goal_id)
            if goal:
                goal.priority = GoalPriority[priority.upper()]
                return f"Приоритет {goal_id} → {priority}"
            return f"Цель {goal_id} не найдена"

        # Decision Loop
        if action == "stop_loop" and self.decision_loop:
            self.decision_loop.stop()
            return "Decision Loop остановлен"

        if action == "start_loop" and self.decision_loop:
            if not self.decision_loop.running:
                asyncio.create_task(self.decision_loop.run())
                return "Decision Loop запущен"
            return "Decision Loop уже работает"

        # Self Healer
        if action == "check_errors" and self.self_healer:
            stats = self.self_healer.get_error_stats()
            return f"Ошибок: {stats['total']}, решено: {stats['resolved']}, нерешено: {stats['unresolved']}"

        # Judge Protocol
        if action == "analyze_niche" and self.judge_protocol:
            topic = params.get("topic", "digital products")
            deep = params.get("deep", False)
            if deep:
                verdict = await self.judge_protocol.evaluate_niche_deep(topic)
            else:
                verdict = await self.judge_protocol.evaluate_niche(topic)
            return self.judge_protocol.format_verdict_for_telegram(verdict)

        # Knowledge Update
        if action == "update_knowledge" and self.knowledge_updater:
            results = await self.knowledge_updater.run_weekly_update()
            return f"Знания обновлены: {json.dumps(results, ensure_ascii=False)[:200]}"

        # Backup
        if action == "create_backup" and self.self_updater:
            path = self.self_updater.backup_current_code()
            return f"Бэкап: {path}" if path else "Бэкап не удался"

        # Code changes
        if action == "apply_code_change" and self.code_generator:
            target_file = params.get("file", "")
            instruction = params.get("instruction", "")
            if not target_file or not instruction:
                return "Нужны параметры: file и instruction"
            result = await self.code_generator.apply_change(target_file, instruction)
            if result.get("success"):
                return f"Код изменён: {target_file}"
            return f"Не удалось изменить: {result.get('error', 'unknown')}"

        if action == "self_improve" and self.agent_registry:
            request = params.get("request", "") or params.get("instruction", "")
            if not request:
                return "Нужен параметр: request"
            result = await self.agent_registry.dispatch("self_improve", step=request)
            if result and result.success:
                return "Self-improve завершён успешно"
            return f"Self-improve завершён с ошибкой: {getattr(result, 'error', 'unknown')}"

        if action == "learn_service" and self.agent_registry:
            service = params.get("service", "") or params.get("name", "")
            if not service:
                return "Нужен параметр: service"
            result = await self.agent_registry.dispatch("learn_service", service=service)
            if result and result.success:
                return f"Знания по сервису {service} обновлены"
            return f"Не удалось изучить сервис: {getattr(result, 'error', 'unknown')}"

        if action == "run_deep_research" and self.agent_registry:
            topic = str(params.get("topic") or "digital products").strip()
            result = await self.agent_registry.dispatch("research", step=topic, topic=topic, goal_title=f"Deep research: {topic[:80]}")
            if result and result.success:
                meta = getattr(result, "metadata", {}) or {}
                summary = str(meta.get("executive_summary") or str(result.output)[:1200])
                verdict = "unknown"
                score = 0
                try:
                    q = await self.agent_registry.dispatch(
                        "quality_review",
                        content=str(result.output)[:6000],
                        content_type="deep_research_report",
                    )
                    if q and q.success and isinstance(getattr(q, "output", None), dict):
                        qout = q.output
                        score = int(qout.get("score", 0) or 0)
                        verdict = "ok" if bool(qout.get("approved", False)) else "rework"
                except Exception:
                    pass
                return (
                    f"Глубокое исследование готово по теме '{topic}'.\n"
                    f"Quality gate: {verdict} (score={score}).\n"
                    f"{summary}"
                )
            return f"Глубокое исследование не удалось: {getattr(result, 'error', 'unknown')}"

        if action == "run_product_pipeline" and self.agent_registry:
            topic = str(params.get("topic") or "Digital Product").strip()
            platforms = params.get("platforms") or [params.get("platform", "gumroad")]
            if isinstance(platforms, str):
                platforms = [p.strip() for p in platforms.split(",") if p.strip()]
            if not isinstance(platforms, list) or not platforms:
                platforms = ["gumroad"]
            auto_publish = bool(params.get("auto_publish", False))
            res = await self.agent_registry.dispatch(
                "product_pipeline",
                topic=topic,
                platform=",".join(platforms),
                auto_publish=auto_publish,
            )
            if res and res.success:
                out = getattr(res, "output", {}) or {}
                done = len([s for s in (out.get("steps") or []) if s.get("ok")])
                total = len(out.get("steps") or [])
                return (
                    f"Product pipeline завершён: {topic}\n"
                    f"- Этапов успешно: {done}/{total}\n"
                    f"- Платформы: {', '.join(platforms)}\n"
                    f"- Auto publish: {'on' if auto_publish else 'off'}"
                )
            return f"Product pipeline завершился с ошибкой: {getattr(res, 'error', 'unknown')}"

        if action == "run_improvement_cycle":
            request = str(params.get("request") or "").strip()
            lines = []
            if self.self_updater:
                try:
                    bkp = self.self_updater.backup_current_code()
                    lines.append(f"Backup: {bkp}" if bkp else "Backup: failed")
                except Exception as e:
                    lines.append(f"Backup error: {e}")
            if self.agent_registry:
                try:
                    hr = await self.agent_registry.dispatch("hr")
                    lines.append("HR audit: ok" if hr and hr.success else f"HR audit: fail ({getattr(hr, 'error', 'unknown')})")
                except Exception as e:
                    lines.append(f"HR audit error: {e}")
                try:
                    rs = await self.agent_registry.dispatch("research", step=request or "agent improvements")
                    lines.append("Research scan: ok" if rs and rs.success else f"Research scan: fail ({getattr(rs, 'error', 'unknown')})")
                except Exception as e:
                    lines.append(f"Research scan error: {e}")
                try:
                    si = await self.agent_registry.dispatch("self_improve", step=request or "Improve weak agent interactions and safety")
                    lines.append("Self-improve: ok" if si and si.success else f"Self-improve: fail ({getattr(si, 'error', 'unknown')})")
                except Exception as e:
                    lines.append(f"Self-improve error: {e}")
            return "Improvement cycle:\n- " + "\n- ".join(lines)

        if action == "autonomous_execute":
            request = str(params.get("request") or "").strip()
            if not request:
                return "Пустой запрос."
            return await self._autonomous_execute(request)

        if action == "register_account" and self.agent_registry:
            url = params.get("url", "")
            form = params.get("form", {}) or {}
            submit_selector = params.get("submit_selector", "")
            code_selector = params.get("code_selector", "")
            code_submit_selector = params.get("code_submit_selector", "")
            if not url or not submit_selector:
                return "Нужны параметры: url и submit_selector"
            result = await self.agent_registry.dispatch(
                "register_with_email",
                url=url,
                form=form,
                submit_selector=submit_selector,
                code_selector=code_selector,
                code_submit_selector=code_submit_selector,
                from_filter=params.get("from_filter", ""),
                subject_filter=params.get("subject_filter", ""),
                prefer_link=bool(params.get("prefer_link", False)),
                timeout_sec=int(params.get("timeout_sec", 180)),
                screenshot_path=params.get("screenshot_path", ""),
            )
            if result and result.success:
                return f"Регистрация выполнена: {str(result.output)[:200]}"
            return f"Регистрация не удалась: {getattr(result, 'error', 'unknown')}"

        return ""

    def _get_available_actions(self) -> str:
        """Список доступных действий для LLM."""
        actions = []
        if self.agent_registry:
            caps = set()
            for a in self.agent_registry.get_all_statuses():
                caps.update(a.get("capabilities", []))
            actions.append(f'dispatch_agent(task_type) — запуск агента (доступные: {", ".join(sorted(caps)[:15])})')
            actions.append("scan_trends() — сканировать тренды")
            actions.append("scan_reddit() — сканировать Reddit")
            actions.append("register_account(url, form, submit_selector, code_selector, ...) — регистрация с email-кодом")
        if self.goal_engine:
            actions.append("cancel_goal(goal_id) — отменить цель")
            actions.append("change_priority(goal_id, priority) — сменить приоритет (CRITICAL/HIGH/MEDIUM/LOW)")
        if self.decision_loop:
            actions.append("stop_loop() — остановить Decision Loop")
            actions.append("start_loop() — запустить Decision Loop")
        if self.self_healer:
            actions.append("check_errors() — проверить ошибки системы")
        if self.judge_protocol:
            actions.append("analyze_niche(topic, deep=false) — анализ ниши (1 модель, deep=true для 4 моделей)")
        if self.knowledge_updater:
            actions.append("update_knowledge() — обновить базу знаний и цены моделей")
        if self.self_updater:
            actions.append("create_backup() — создать бэкап кода")
        if self.code_generator:
            actions.append("apply_code_change(file, instruction) — изменить код файла через LLM (backup + test)")
        if self.agent_registry:
            actions.append("self_improve(request) — самонастройка: анализ → код → тесты")
            actions.append("learn_service(service) — изучить сервис и добавить в базу знаний")
            actions.append("run_deep_research(topic) — глубокое исследование с источниками")
            actions.append("run_product_pipeline(topic, platforms, auto_publish=false) — сквозной pipeline товара")
            actions.append("run_improvement_cycle(request) — backup + HR + research + self-improve")
            actions.append("autonomous_execute(request) — выполнить задачу или доучиться и выполнить")
        return "\n".join(f"  - {a}" for a in actions) if actions else "(нет действий)"

    def _allowed_actions(self) -> set[str]:
        """Allowlist of actions based on connected modules."""
        allowed: set[str] = set()
        if self.agent_registry:
            allowed.update({"dispatch_agent", "scan_trends", "scan_reddit"})
        if self.goal_engine:
            allowed.update({"cancel_goal", "change_priority"})
        if self.decision_loop:
            allowed.update({"stop_loop", "start_loop"})
        if self.self_healer:
            allowed.add("check_errors")
        if self.judge_protocol:
            allowed.add("analyze_niche")
        if self.knowledge_updater:
            allowed.add("update_knowledge")
        if self.self_updater:
            allowed.add("create_backup")
        if self.code_generator:
            allowed.add("apply_code_change")
        if self.agent_registry:
            allowed.add("self_improve")
            allowed.add("learn_service")
            allowed.add("register_account")
            allowed.add("run_deep_research")
            allowed.add("run_product_pipeline")
            allowed.add("run_improvement_cycle")
            allowed.add("autonomous_execute")
        return allowed

    async def _autonomous_execute(self, request: str) -> str:
        """Owner request loop: execute with current skills, else learn and retry."""
        if not self.agent_registry:
            return "AgentRegistry недоступен."

        capability = self._infer_capability(request)
        attempts: list[str] = []

        async def _run_cap(cap: str) -> tuple[bool, str]:
            if not cap:
                return False, "capability_not_detected"
            try:
                res = await self.agent_registry.dispatch(cap, step=request, content=request, goal_title=request[:120])
            except Exception as e:
                return False, f"dispatch_exception:{e}"
            if res and res.success:
                out = getattr(res, "output", None)
                txt = str(out)[:900] if out is not None else "completed"
                return True, txt
            return False, getattr(res, "error", "dispatch_failed") if res else "dispatch_none"

        ok, detail = await _run_cap(capability)
        attempts.append(f"run:{capability or 'unknown'}:{'ok' if ok else detail}")
        if ok:
            self._record_autonomy_learning(
                request=request,
                capability=capability or "unknown",
                success=True,
                attempts=attempts,
                result_text=detail,
            )
            return f"Задача выполнена ({capability}).\nРезультат: {detail}"

        if bool(getattr(settings, "AUTONOMY_AUTO_LEARN_ON_FAILURE", True)):
            # Learn via research agent and retry (cheap + robust).
            try:
                rr = await self.agent_registry.dispatch("research", step=request, topic=request, goal_title=f"Auto-learn: {request[:80]}")
                attempts.append(f"learn:research:{'ok' if rr and rr.success else 'fail'}")
            except Exception as e:
                attempts.append(f"learn:research_exception:{e}")

        if bool(getattr(settings, "AUTONOMY_AUTO_SELF_IMPROVE_ON_MISS", False)):
            try:
                si = await self.agent_registry.dispatch("self_improve", step=f"Improve capability for request: {request}")
                attempts.append(f"learn:self_improve:{'ok' if si and si.success else 'fail'}")
            except Exception as e:
                attempts.append(f"learn:self_improve_exception:{e}")

        # Retry with same capability or fallback orchestrate.
        ok2, detail2 = await _run_cap(capability)
        attempts.append(f"retry:{capability or 'unknown'}:{'ok' if ok2 else detail2}")
        if ok2:
            self._record_autonomy_learning(
                request=request,
                capability=capability or "unknown",
                success=True,
                attempts=attempts,
                result_text=detail2,
            )
            return (
                f"Задача выполнена после обучения ({capability}).\n"
                f"Результат: {detail2}\n"
                f"Шаги: {' | '.join(attempts)}"
            )

        # Last fallback: core orchestrator.
        try:
            core = self.agent_registry.get("vito_core") if hasattr(self.agent_registry, "get") else None
            if core is not None:
                res = await core.execute_task("orchestrate", step=request, goal_title=request[:120])
                if res and res.success:
                    self._record_autonomy_learning(
                        request=request,
                        capability="orchestrate",
                        success=True,
                        attempts=attempts,
                        result_text=str(getattr(res, "output", "")),
                    )
                    return (
                        "Задача выполнена через оркестратор.\n"
                        f"Результат: {str(getattr(res, 'output', ''))[:900]}\n"
                        f"Шаги: {' | '.join(attempts)}"
                    )
        except Exception as e:
            attempts.append(f"fallback:orchestrate_exception:{e}")

        self._record_autonomy_learning(
            request=request,
            capability=capability or "unknown",
            success=False,
            attempts=attempts,
            result_text="",
        )
        return (
            "Автономный контур не смог завершить задачу с текущими навыками.\n"
            "Я сохранил попытки в память ошибок и продолжу дообучение по этой теме.\n"
            f"Шаги: {' | '.join(attempts[:8])}"
        )

    def _infer_capability(self, request: str) -> str:
        text = str(request or "").strip()
        if not text:
            return ""
        try:
            core = self.agent_registry.get("vito_core") if hasattr(self.agent_registry, "get") else None
            if core and hasattr(core, "classify_step"):
                cap = core.classify_step(text)
                if cap:
                    return str(cap)
        except Exception:
            pass
        # Heuristic fallback map.
        s = self._normalize_for_nlu(text)
        mapping = [
            (("исслед", "research", "анализ", "deep"), "research"),
            (("тренд", "niche", "ниш"), "trend_scan"),
            (("seo", "ключев", "keyword", "мета"), "listing_seo_pack"),
            (("пост", "tweet", "соц", "smm"), "social_media"),
            (("товар", "листинг", "publish", "продукт"), "product_pipeline"),
            (("перевод", "translate", "localize"), "translate"),
            (("юрид", "tos", "gdpr", "copyright"), "legal"),
            (("финанс", "юнит", "цена", "pricing"), "unit_economics"),
            (("документ", "report", "отчет"), "documentation"),
        ]
        for keys, cap in mapping:
            if any(k in s for k in keys):
                return cap
        return "orchestrate"

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
        s = str(text or "").strip()
        s = re.sub(r"(?i)\b(проведи|сделай|запусти|выполни)\b", "", s).strip()
        s = re.sub(r"(?i)\b(глубокое|глубокий|deep)\b", "", s).strip()
        s = re.sub(r"(?i)\b(исследование|анализ|research)\b", "", s).strip(" :,-")
        return s or "digital product niches for US market"

    @staticmethod
    def _extract_product_topic(text: str) -> str:
        s = str(text or "").strip()
        # remove imperative wrappers
        s = re.sub(r"(?i)\b(сделай|создай|запусти|подготовь|оформи)\b", "", s).strip()
        s = re.sub(r"(?i)\b(товар|продукт|под ключ|turnkey|pipeline)\b", "", s).strip(" :,-")
        return s or "Digital Product Starter Kit"

    @staticmethod
    def _extract_platforms(text: str) -> list[str]:
        s = str(text or "").lower()
        out: list[str] = []
        for k, v in (
            ("gumroad", "gumroad"),
            ("гумроад", "gumroad"),
            ("etsy", "etsy"),
            ("этси", "etsy"),
            ("етси", "etsy"),
            ("kofi", "kofi"),
            ("ko-fi", "kofi"),
            ("кофи", "kofi"),
            ("amazon", "amazon_kdp"),
            ("kdp", "amazon_kdp"),
            ("амазон", "amazon_kdp"),
        ):
            if k in s and v not in out:
                out.append(v)
        return out or ["gumroad"]

    @staticmethod
    def _is_time_query(lower: str) -> bool:
        time_words = ("время", "час", "дата", "time", "what time", "date", "сколько время")
        return any(w in lower for w in time_words) and len(lower) < 60

    @staticmethod
    def _format_time_answer() -> str:
        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now()
        return (
            f"Сейчас: {now_local.strftime('%Y-%m-%d %H:%M')} (локальное время сервера)\n"
            f"UTC: {now_utc.strftime('%Y-%m-%d %H:%M')}\n"
            f"День недели: {now_utc.strftime('%A')}"
        )

    def _quick_answer(self, lower: str) -> str:
        if any(w in lower for w in ("статус", "status", "health")):
            return self._quick_status()
        if any(w in lower for w in ("расход", "spend", "budget", "лимит")):
            return self._quick_spend()
        if any(w in lower for w in ("pnl", "прибыл", "доход", "revenue")):
            return self._quick_pnl()
        if any(w in lower for w in ("balances", "баланс", "остатки", "счета")):
            return self._quick_balances()
        if any(w in lower for w in ("цели", "goals", "задачи", "tasks")):
            return self._quick_goals()
        if any(w in lower for w in ("агенты", "agents", "команда")):
            return self._quick_agents()
        if any(w in lower for w in ("ошибк", "errors")):
            return self._quick_errors()
        if any(w in lower for w in ("календар", "calendar", "сегодняшняя задача", "task today")):
            return self._quick_calendar()

        if any(w in lower for w in ("праздник", "holiday", "календар")):
            try:
                from modules.calendar_knowledge import search_calendar, format_calendar_results
                results = search_calendar(text)
                return format_calendar_results(results)
            except Exception:
                pass
        else:
            # If explicit date in message, try calendar lookup
            try:
                from modules.calendar_knowledge import search_calendar, format_calendar_results
                results = search_calendar(text)
                if results:
                    return format_calendar_results(results)
            except Exception:
                pass
        if any(w in lower for w in ("skills", "навык")):
            return self._quick_skills()
        if any(w in lower for w in ("обновлен", "updates", "апдейт")):
            return self._quick_updates()
        return ""

    def _quick_status(self) -> str:
        parts = ["VITO Status (fast)"]
        if self.decision_loop:
            st = self.decision_loop.get_status()
            parts.append(
                f"Decision Loop: {'работает' if st['running'] else 'остановлен'} "
                f"(тики: {st['tick_count']}, spend: ${st['daily_spend']:.2f})"
            )
        if self.goal_engine:
            gs = self.goal_engine.get_stats()
            parts.append(
                f"Цели: {gs['total']} всего, {gs['completed']} выполнено, "
                f"{gs['executing']} в работе, {gs['pending']} ожидают"
            )
        if self.comms:
            pending = len(getattr(self.comms, "_pending_approvals", {}) or {})
            if pending:
                parts.append(f"Ожидают одобрения: {pending}")
        if self.owner_task_state:
            try:
                active = self.owner_task_state.get_active()
                if active:
                    parts.append(f"Активная задача владельца: {str(active.get('text', ''))[:120]}")
            except Exception:
                pass
        return "\n".join(parts)

    def _quick_spend(self) -> str:
        spend = self.llm_router.get_daily_spend() if self.llm_router else 0.0
        limit = settings.DAILY_LIMIT_USD
        return f"Расходы сегодня: ${spend:.2f} / ${limit:.2f} (осталось ${max(limit - spend, 0):.2f})"

    def _quick_pnl(self) -> str:
        if not self.finance:
            return "FinancialController не подключён."
        pnl = self.finance.get_pnl(days=30)
        return (
            f"P&L за 30 дней: расход ${pnl['total_expenses']:.2f}, "
            f"доход ${pnl['total_income']:.2f}, "
            f"{'прибыль' if pnl['profitable'] else 'убыток'} ${abs(pnl['net_profit']):.2f}"
        )

    def _quick_balances(self) -> str:
        if not self.finance:
            return "FinancialController не подключён."
        daily_spent = self.finance.get_daily_spent()
        daily_earned = self.finance.get_daily_earned()
        limit = settings.DAILY_LIMIT_USD
        return (
            f"Внутренние балансы (без внешних API):\n"
            f"- Потрачено сегодня: ${daily_spent:.2f}\n"
            f"- Доход сегодня: ${daily_earned:.2f}\n"
            f"- Лимит: ${limit:.2f} (осталось ${max(limit - daily_spent, 0):.2f})"
        )

    def _quick_goals(self) -> str:
        if not self.goal_engine:
            return "GoalEngine не подключён."
        goals = self.goal_engine.get_all_goals()[:10]
        if not goals:
            return "Нет целей."
        lines = []
        for g in goals:
            icon = {"completed": "done", "failed": "fail", "executing": ">>",
                    "pending": "..", "waiting_approval": "??", "planning": "~~"}.get(
                g.status.value, g.status.value
            )
            lines.append(f"[{icon}] {g.title} (${g.estimated_cost_usd:.2f})")
        return "Цели:\n" + "\n".join(lines)

    def _quick_agents(self) -> str:
        if not self.agent_registry:
            return "AgentRegistry не подключён."
        statuses = self.agent_registry.get_all_statuses()
        if not statuses:
            return "Нет зарегистрированных агентов."
        lines = [f"Агенты ({len(statuses)}):"]
        for s in statuses:
            icon = {"idle": "o", "running": ">>", "stopped": "x", "error": "!"}.get(s["status"], "?")
            lines.append(f"[{icon}] {s['name']} — {s['status']}")
        return "\n".join(lines)

    def _quick_errors(self) -> str:
        if not self.self_healer:
            return "SelfHealer не подключён."
        stats = self.self_healer.get_error_stats()
        unresolved = stats.get("unresolved", 0)
        return (
            f"Ошибки: всего {stats.get('total', 0)}, "
            f"нерешено {unresolved}, решено {stats.get('resolved', 0)}"
        )

    def _quick_calendar(self) -> str:
        try:
            import sqlite3
            conn = sqlite3.connect(settings.SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT * FROM weekly_calendar WHERE date = ? LIMIT 1",
                (today,),
            ).fetchone()
            conn.close()
            if row:
                return f"Сегодня: {row['title']} — {row['description'][:200]}"
            return "Сегодня в календаре задач нет."
        except Exception:
            return "Календарь недоступен."

    def _quick_skills(self) -> str:
        if not self.memory:
            return "Memory не подключена."
        skills = self.memory.get_top_skills(limit=5)
        if not skills:
            return "Навыки пока не накоплены."
        lines = [f"{s['name']}: успех {s.get('success_count', 0)}, провал {s.get('fail_count', 0)}" for s in skills]
        return "Топ навыки:\n" + "\n".join(lines)

    def _quick_updates(self) -> str:
        if not self.self_updater:
            return "SelfUpdater не подключён."
        history = self.self_updater.get_update_history(limit=3)
        if not history:
            return "История обновлений пуста."
        lines = [f"{h.get('timestamp', '?')}: {h.get('description', '')[:80]}" for h in history]
        return "Последние обновления:\n" + "\n".join(lines)

    # ── Полное состояние системы ──

    def _format_system_context(self) -> str:
        """ПОЛНЫЙ контекст: расходы, модели, финансы, цели, агенты, ошибки, навыки."""
        parts = []

        # 0. Time awareness (no LLM)
        now = datetime.now(timezone.utc)
        parts.append(
            f"Текущее время: {now.strftime('%Y-%m-%d %H:%M UTC')} "
            f"({now.strftime('%A')})"
        )

        # 1. Расходы по моделям (из spend_log)
        try:
            daily_spend = self.llm_router.get_daily_spend()
            breakdown = self.llm_router.get_spend_breakdown(days=1)
            spend_lines = [f"LLM расходы сегодня: ${daily_spend:.4f} / ${settings.DAILY_LIMIT_USD:.2f} "
                           f"(осталось: ${max(settings.DAILY_LIMIT_USD - daily_spend, 0):.4f})"]
            if breakdown:
                for row in breakdown:
                    spend_lines.append(
                        f"  {row['model']} [{row['task_type']}]: ${row['total_cost']:.4f} "
                        f"({row['calls']} вызовов, {row['total_input']}+{row['total_output']} токенов)"
                    )
            else:
                spend_lines.append("  (нет вызовов сегодня)")
            parts.append("\n".join(spend_lines))
        except Exception:
            pass

        # 2. Доступные модели с ценами
        try:
            model_lines = ["Доступные модели:"]
            for key, m in MODEL_REGISTRY.items():
                model_lines.append(
                    f"  {m.display_name} ({m.provider}): "
                    f"${m.cost_per_1k_input:.4f}/1K in, ${m.cost_per_1k_output:.4f}/1K out"
                )
            parts.append("\n".join(model_lines))
        except Exception:
            pass

        # 3. Финансы
        if self.finance:
            try:
                daily_spent = self.finance.get_daily_spent()
                daily_earned = self.finance.get_daily_earned()
                by_agent = self.finance.get_spend_by_agent(days=1)
                by_cat = self.finance.get_spend_by_category(days=1)
                pnl = self.finance.get_pnl(days=7)
                products = self.finance.get_product_roi()

                fin_lines = [f"Финансы: потрачено ${daily_spent:.4f}, заработано ${daily_earned:.2f}"]
                if by_agent:
                    fin_lines.append("  По агентам:")
                    for a in by_agent[:7]:
                        fin_lines.append(f"    {a['agent']}: ${a['total']:.4f} ({a['calls']} операций)")
                if by_cat:
                    fin_lines.append("  По категориям:")
                    for c in by_cat[:5]:
                        fin_lines.append(f"    {c['category']}: ${c['total']:.4f}")
                fin_lines.append(
                    f"  P&L 7 дней: расход ${pnl['total_expenses']:.4f}, "
                    f"доход ${pnl['total_income']:.2f}, "
                    f"{'прибыль' if pnl['profitable'] else 'убыток'} ${abs(pnl['net_profit']):.4f}"
                )
                if products:
                    fin_lines.append("  Продукты:")
                    for p in products[:5]:
                        fin_lines.append(
                            f"    {p['name']} ({p['platform']}): "
                            f"доход ${p['revenue']:.2f}, ROI {p['roi_pct']:.0f}%"
                        )
                parts.append("\n".join(fin_lines))
            except Exception:
                pass

        # 4. Цели (все, не только активные)
        if self.goal_engine:
            try:
                stats = self.goal_engine.get_stats()
                goals = self.goal_engine.get_all_goals()
                goal_lines = [
                    f"Цели: всего {stats['total']}, выполнено {stats['completed']}, "
                    f"в работе {stats['executing']}, ожидают {stats['pending']}, "
                    f"провалено {stats['failed']}, успешность {stats['success_rate']:.0%}"
                ]
                for g in goals[:12]:
                    icon = {"completed": "OK", "failed": "XX", "executing": ">>",
                            "pending": "..", "waiting_approval": "??", "planning": "~~",
                            "cancelled": "--"}.get(g.status.value, g.status.value)
                    goal_lines.append(
                        f"  [{icon}] {g.goal_id[:8]} | {g.title} "
                        f"(приоритет: {g.priority.name}, ${g.estimated_cost_usd:.2f})"
                    )
                parts.append("\n".join(goal_lines))
            except Exception:
                pass

        # 4.5 Active owner task (persisted across messages/sessions)
        if self.owner_task_state:
            try:
                active = self.owner_task_state.get_active()
                if active:
                    parts.append(
                        "Активная задача владельца:\n"
                        f"  text: {str(active.get('text', ''))[:300]}\n"
                        f"  intent: {str(active.get('intent', ''))}\n"
                        f"  status: {str(active.get('status', 'active'))}\n"
                        f"  updated_at: {str(active.get('updated_at', ''))}"
                    )
            except Exception:
                pass

        # 5. Агенты (все 23)
        if self.agent_registry:
            try:
                statuses = self.agent_registry.get_all_statuses()
                running = [s for s in statuses if s.get("status") == "running"]
                idle = [s for s in statuses if s.get("status") == "idle"]
                agent_lines = [f"Агенты: {len(statuses)} всего, {len(running)} работают, {len(idle)} ожидают"]
                for s in statuses:
                    completed = s.get("tasks_completed", 0)
                    cost = s.get("total_cost", 0)
                    if completed > 0 or s.get("status") == "running":
                        agent_lines.append(
                            f"  {s['name']}: {s['status']} "
                            f"(задач: {completed}, ${cost:.4f})"
                        )
                parts.append("\n".join(agent_lines))
            except Exception:
                pass

        # 6. Decision Loop
        if self.decision_loop:
            try:
                dl = self.decision_loop.get_status()
                parts.append(
                    f"Decision Loop: {'РАБОТАЕТ' if dl['running'] else 'ОСТАНОВЛЕН'}, "
                    f"тиков: {dl['tick_count']}, потрачено: ${dl['daily_spend']:.4f}"
                )
            except Exception:
                pass

        # 7. Ошибки (SelfHealer)
        if self.self_healer:
            try:
                err = self.self_healer.get_error_stats()
                err_lines = [
                    f"Ошибки: {err['total']} всего, решено {err['resolved']}, "
                    f"нерешено {err['unresolved']}, процент решения {err.get('resolution_rate', 0):.0%}"
                ]
                for e in err.get("recent", [])[:3]:
                    if not e.get("resolved"):
                        err_lines.append(
                            f"  [{e.get('module', '?')}] {e.get('error_type', '?')}: "
                            f"{e.get('message', '?')[:80]}"
                        )
                parts.append("\n".join(err_lines))
            except Exception:
                pass

        # 8. Навыки (топ из памяти)
        if self.memory:
            try:
                skills = self.memory.get_top_skills(limit=5)
                if skills:
                    skill_lines = ["Топ навыки:"]
                    for s in skills:
                        skill_lines.append(
                            f"  {s['name']}: успех {s.get('success_count', 0)}, "
                            f"провал {s.get('fail_count', 0)}"
                        )
                    parts.append("\n".join(skill_lines))
            except Exception:
                pass
        # 8.1 Предпочтения владельца (кратко)
        try:
            prefs = OwnerPreferenceModel().list_preferences(limit=5)
            if prefs:
                pref_line = "; ".join(f"{p.get('pref_key')}={p.get('value')}" for p in prefs)
                parts.append(f"Предпочтения владельца: {pref_line}")
        except Exception:
            pass

        # 9. Обновления (SelfUpdater)
        if self.self_updater:
            try:
                history = self.self_updater.get_update_history(limit=3)
                if history:
                    upd_lines = ["Последние обновления:"]
                    for h in history:
                        upd_lines.append(
                            f"  {h.get('timestamp', '?')}: {h.get('description', '?')[:60]}"
                        )
                    parts.append("\n".join(upd_lines))
            except Exception:
                pass

        return "\n\n".join(parts) if parts else "(система не инициализирована)"

    # ── Утилиты ──

    def _extract_json(self, text: str) -> Optional[dict]:
        """Извлекает JSON из ответа LLM."""
        parsed = text.strip()
        if "```" in parsed:
            for block in parsed.split("```"):
                block = block.strip()
                if block.startswith("json"):
                    block = block[4:].strip()
                if block.startswith("{"):
                    parsed = block
                    break
        if parsed.startswith("{"):
            return json.loads(parsed)
        return None

    def _add_turn(self, role: str, text: str, intent: Optional[Intent] = None) -> None:
        turn = Turn(role=role, text=text, intent=intent)
        self._context.append(turn)
        if len(self._context) > MAX_CONTEXT_TURNS:
            self._context = self._context[-MAX_CONTEXT_TURNS:]
        self._persist_turn(turn)

    def _format_context(self) -> str:
        if not self._context:
            return "(начало разговора)"
        turns = max(5, min(20, int(getattr(settings, "CONVERSATION_CONTEXT_TURNS", 10) or 10)))
        lines = []
        for turn in self._context[-turns:]:
            role_label = "Владелец" if turn.role == "user" else "VITO"
            lines.append(f"{role_label}: {turn.text[:200]}")
        return "\n".join(lines)

    def _owner_task_focus_text(self) -> str:
        if not self.owner_task_state:
            return "Фокус владельца: (не зафиксирован)"
        try:
            active = self.owner_task_state.get_active()
            if not active:
                return "Фокус владельца: (не зафиксирован)"
            return (
                "Фокус владельца:\n"
                f"- текущая задача: {str(active.get('text', ''))[:260]}\n"
                f"- intent: {str(active.get('intent', ''))[:80]}\n"
                f"- статус: {str(active.get('status', 'active'))[:40]}"
            )
        except Exception:
            return "Фокус владельца: (не зафиксирован)"

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
        if not self.conversation_memory:
            return
        entries = self.conversation_memory.load(limit=MAX_CONTEXT_TURNS, session_id=self._session_id)
        loaded: list[Turn] = []
        for entry in entries:
            turn = self._turn_from_entry(entry)
            if turn:
                loaded.append(turn)
        self._context = loaded[-MAX_CONTEXT_TURNS:]

    def _turn_from_entry(self, entry: dict) -> Turn | None:
        role = entry.get("role")
        text = entry.get("text")
        if not role or not text:
            return None
        intent_value = entry.get("intent")
        timestamp = entry.get("timestamp")
        intent = None
        if intent_value:
            try:
                intent = Intent(intent_value)
            except ValueError:
                intent = None
        try:
            ts = datetime.fromisoformat(timestamp) if timestamp else datetime.now(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)
        return Turn(role=role, text=text, intent=intent, timestamp=ts)

    def _persist_turn(self, turn: Turn) -> None:
        if not self.conversation_memory:
            return
        entry = {
            "role": turn.role,
            "text": turn.text,
            "intent": turn.intent.value if turn.intent else None,
            "timestamp": turn.timestamp.isoformat(),
        }
        try:
            self.conversation_memory.append(entry, session_id=self._session_id)
        except Exception:
            pass
