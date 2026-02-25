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
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings
from modules.owner_preference_model import OwnerPreferenceModel
from llm_router import LLMRouter, TaskType, MODEL_REGISTRY
from modules.prompt_guard import wrap_untrusted_text

logger = get_logger("conversation_engine", agent="conversation_engine")

VITO_PERSONALITY = (
    "Ты VITO — автономный AI-агент, бизнес-партнёр владельца. "
    "Отвечай на русском, коротко и по делу.\n\n"
    "СТРОГИЕ ПРАВИЛА КОММУНИКАЦИИ:\n"
    "1. Максимум 5-7 строк. Ни слова лишнего.\n"
    "2. ТОЛЬКО по теме разговора. Обсуждаем контент → ни слова про финансы/ошибки/агентов. "
    "Обсуждаем расходы → ни слова про тренды/контент.\n"
    "3. НИКОГДА не кидай файловые пути (/home/...). Покажи текст прямо в сообщении.\n"
    "4. Если создал контент — покажи его текст целиком, не ссылайся на файл.\n"
    "5. Не сбрасывай JSON, логи, сырые данные, ID задач.\n"
    "6. Предлагай варианты: 'A или B? Что выбираешь?'\n"
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
                 code_generator=None, comms=None):
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
        self._context: list[Turn] = []
        logger.info("ConversationEngine инициализирован", extra={"event": "init"})

    async def process_message(self, text: str) -> dict[str, Any]:
        """Обрабатывает сообщение от владельца."""
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
                            "intent": Intent.QUESTION,
                        }
                if any(k in lower for k in ("текст", "прочитай", "extract", "вытащи", "что написано")):
                    task_type = "web_scrape"
                    result = await self.agent_registry.dispatch(task_type, url=url, selector="body")
                    if result and result.success:
                        return {
                            "response": f"Текст со страницы:\n{str(result.output)[:3500]}",
                            "intent": Intent.QUESTION,
                        }
                # default: quick browse (title + status)
                result = await self.agent_registry.dispatch("browse", url=url)
                if result and result.success:
                    out = result.output or {}
                    title = out.get("title", "")
                    status = out.get("status", "")
                    return {"response": f"Страница открыта. {title} (HTTP {status})", "intent": Intent.QUESTION}
            except Exception:
                pass

        # Fallback: fetch URL without LLM (free web fetch)
        if "http://" in text or "https://" in text:
            try:
                import re
                from modules.web_fetch import fetch_url
                m = re.search(r"https?://\\S+", text)
                if m:
                    url = m.group(0).rstrip(".,)")
                    data = fetch_url(url)
                    response = f"URL: {url}\nTitle: {data.get('title','')}\n\n{data.get('text','')}"
                    return {"response": response, "intent": Intent.QUESTION}
            except Exception:
                pass
        # 1. Detect intent
        intent = self._detect_intent_rules(text)
        if intent is None:
            intent = await self._detect_intent_llm(text)

        # 2. Save user turn
        self._add_turn("user", text, intent)

        # 2.5. Сохраняем важные запросы владельца в долгосрочную память
        if intent in (Intent.GOAL_REQUEST, Intent.QUESTION, Intent.SYSTEM_ACTION) and self.memory:
            try:
                self.memory.store_knowledge(
                    doc_id=f"user_msg_{int(time.time())}",
                    text=f"Владелец: {text}",
                    metadata={"type": "user_request", "intent": intent.value},
                )
            except Exception:
                pass

        # 3. Process by intent
        result = await self._process_by_intent(intent, text)

        # 4. Execute actions if LLM requested them
        if result.get("actions"):
            action_results = await self._execute_actions(result["actions"])
            if action_results:
                result["response"] = (result.get("response") or "") + "\n\n" + action_results

        # 5. Save assistant turn
        if result.get("response"):
            self._add_turn("assistant", result["response"])

        return result

    def _detect_intent_rules(self, text: str) -> Optional[Intent]:
        """Rule-based intent detection (быстрый первый фильтр)."""
        stripped = text.strip()

        if stripped.startswith("/"):
            return Intent.COMMAND

        lower = stripped.lower()
        # Explicit question markers override goal detection
        if "?" in stripped:
            return Intent.QUESTION
        if lower.startswith(("откуда", "почему", "зачем", "как", "кто", "что", "где", "когда", "какой", "какие", "чем")):
            return Intent.QUESTION

        # Time queries — no LLM needed
        time_words = ("время", "час", "дата", "time", "what time", "date", "сколько время")
        if any(w in lower for w in time_words) and len(lower) < 40:
            return Intent.QUESTION
        approval_words = {"да", "нет", "ок", "ok", "yes", "no", "approve", "reject",
                          "отмена", "одобряю", "отклоняю"}
        if lower in approval_words:
            return Intent.APPROVAL

        # Goal request keywords (product creation, tasks, publishing)
        goal_keywords = [
            "создай", "сделай", "опубликуй", "напиши", "разработай",
            "запусти продукт", "запусти товар", "продукт", "ebook",
            "create", "make", "publish", "build", "launch",
            "write an", "write a", "design", "generate",
        ]
        if any(kw in lower for kw in goal_keywords):
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
        if any(kw in lower for kw in self_improve_keywords):
            return Intent.SYSTEM_ACTION
        if any(kw in lower for kw in learn_service_keywords):
            return Intent.SYSTEM_ACTION
        if any(kw in lower for kw in action_keywords):
            return Intent.SYSTEM_ACTION

        return None

    @staticmethod
    def _extract_url(text: str) -> Optional[str]:
        import re
        # Full URL
        m = re.search(r"https?://\\S+", text)
        if m:
            return m.group(0).rstrip(".,)")
        # Bare domain (avoid emails)
        m = re.search(r"\\b([a-z0-9.-]+\\.[a-z]{2,})(/[^\\s]*)?\\b", text, re.IGNORECASE)
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
        # Direct answer for "source of claim" questions to avoid hallucinations
        if any(w in lower for w in ("откуда", "почему ты", "почему вы", "ты писал", "ты написал", "ты сказала", "ты говорил")):
            return {
                "intent": Intent.QUESTION.value,
                "response": "У меня нет подтверждённых данных о публикации/создании. Это было ошибочное сообщение. Исправляю: без факта выполнения больше так не пишу.",
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

    async def _handle_system_action(self, text: str) -> dict[str, Any]:
        """Выполняет системное действие по запросу владельца."""
        system_context = self._format_system_context()
        available_actions = self._get_available_actions()

        # Fast path for explicit self-improve requests
        lower = text.lower()
        self_improve_keywords = [
            "исправь", "почини", "доработай", "улучши код", "улучши",
            "самоисправ", "добавь интеграц", "сделай интеграц",
            "добавь поддержку", "добавь навык",
        ]
        if any(kw in lower for kw in self_improve_keywords):
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": "Запускаю self-improve пайплайн (анализ → код → тесты).",
                "actions": [{"action": "self_improve", "params": {"request": text}}],
            }
        if any(kw in lower for kw in ["изучи сервис", "изучи платформ", "добавь знания", "найди требования"]):
            # crude extraction of service name from text
            service = text.replace("изучи", "").replace("платформу", "").replace("сервис", "").strip()
            return {
                "intent": Intent.SYSTEM_ACTION.value,
                "response": "Изучаю сервис и добавляю знания в базу.",
                "actions": [{"action": "learn_service", "params": {"service": service}}],
            }

        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
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

        return {
            "intent": Intent.SYSTEM_ACTION.value,
            "response": reply,
            "actions": actions,
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
                    for pr in pref_rows:
                        conf = float(pr.get("confidence", 0))
                        val = pr.get("value")
                        lines.append(f"- {pr.get('pref_key')}: {val} (conf={conf:.2f})")
                    owner_prefs = owner_prefs + "\n" + "\n".join(lines) if owner_prefs else "\nПредпочтения владельца:\n" + "\n".join(lines)
            except Exception:
                pass

        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
            f"{skills_context}{owner_prefs}\n\n"
            f"Владелец просит: \"{wrap_untrusted_text(text)}\"\n\n"
            f"ПРАВИЛА:\n"
            f"1. Все продукты/контент — на АНГЛИЙСКОМ (US/CA/EU market)\n"
            f"2. НЕ начинай сразу. Сформируй план и предложи на одобрение\n"
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
            f'"confirmation": "предложение владельцу на русском: вот план, что думаешь?", '
            f'"needs_approval": true, '
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
        confirmation = f"Принял задачу: \"{goal_title}\"\n\nГотовлю план. Отправлю на одобрение."
        priority = "HIGH"
        needs_approval = True
        estimated_cost = 0.05

        if response:
            try:
                data = self._extract_json(response)
                if data:
                    goal_title = data.get("goal_title", goal_title)
                    goal_description = data.get("goal_description", text)
                    confirmation = data.get("confirmation", confirmation)
                    priority = data.get("priority", "HIGH")
                    needs_approval = data.get("needs_approval", True)
                    estimated_cost = data.get("estimated_cost_usd", 0.05)
            except Exception:
                pass

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
                    return "Это было предложение, а не факт выполнения. Подтвердить запуск?"
            except Exception:
                return "Это было предложение, а не факт выполнения. Подтвердить запуск?"
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
                    # Auto self-improve for missing actions requested by owner
                    if self.agent_registry:
                        try:
                            await self.agent_registry.dispatch(
                                "self_improve",
                                step=f"Implement missing system action '{action_name}' to satisfy owner request.",
                                goal_title="auto_self_improve",
                            )
                            results.append(f"[{action_name}] Auto self-improve triggered")
                            continue
                        except Exception:
                            pass
                    results.append(f"[{action_name}] Действие запрещено allowlist")
                    continue
                if action_name == "apply_code_change":
                    if not self.comms:
                        results.append("[apply_code_change] Approval channel unavailable")
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
                        results.append("[apply_code_change] Owner approval rejected or timed out")
                        continue
                result = await self._dispatch_action(action_name, params)
                if result:
                    results.append(f"[{action_name}] {result}")
            except Exception as e:
                results.append(f"[{action_name}] Ошибка: {e}")
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
        return allowed

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
        self._context.append(Turn(role=role, text=text, intent=intent))
        if len(self._context) > MAX_CONTEXT_TURNS:
            self._context = self._context[-MAX_CONTEXT_TURNS:]

    def _format_context(self) -> str:
        if not self._context:
            return "(начало разговора)"
        lines = []
        for turn in self._context[-10:]:
            role_label = "Владелец" if turn.role == "user" else "VITO"
            lines.append(f"{role_label}: {turn.text[:200]}")
        return "\n".join(lines)

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
