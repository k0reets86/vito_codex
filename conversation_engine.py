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
from llm_router import LLMRouter, TaskType, MODEL_REGISTRY

logger = get_logger("conversation_engine", agent="conversation_engine")

VITO_PERSONALITY = (
    "Ты VITO — автономный AI-агент с ПОЛНЫМ доступом ко всем системам. "
    "Ты видишь ВСЕ данные: расходы по каждой модели, каждый API-вызов, "
    "состояние всех 23 агентов, все цели, ошибки, навыки, тренды. "
    "Ты можешь ВЫПОЛНЯТЬ действия: запускать агентов, сканировать тренды, "
    "менять приоритеты целей, анализировать ниши. "
    "Отвечай на русском. Давай КОНКРЕТНЫЕ цифры и данные из системы. "
    "Не говори 'я не могу посмотреть' — ты ВСЁ видишь. "
    "Тон: дружелюбный, деловой, без лишней воды.\n\n"
    "ВАЖНО — ПРАВИЛА СОЗДАНИЯ КОНТЕНТА:\n"
    "1. Все цифровые продукты, описания, статьи — ТОЛЬКО на АНГЛИЙСКОМ языке. "
    "Целевой рынок: US, Canada, EU. Русский — только для общения с владельцем.\n"
    "2. Workflow для продуктов: идея → утверждение владельцем → создание → "
    "утверждение готового продукта → публикация → линк.\n"
    "3. Правило 'не уверен — спроси': если неопределённость > 40%, "
    "спроси владельца перед действием. Со временем учись его предпочтениям."
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
                 code_generator=None):
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
        self._context: list[Turn] = []
        logger.info("ConversationEngine инициализирован", extra={"event": "init"})

    async def process_message(self, text: str) -> dict[str, Any]:
        """Обрабатывает сообщение от владельца."""
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
        if any(kw in lower for kw in action_keywords):
            return Intent.SYSTEM_ACTION

        return None

    async def _detect_intent_llm(self, text: str) -> Intent:
        """LLM-based intent detection через Haiku (~50 токенов)."""
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
                return intent_map.get(intent_str, Intent.CONVERSATION)
        except Exception as e:
            logger.debug(f"LLM intent detection failed: {e}", extra={"event": "intent_llm_error"})

        return Intent.CONVERSATION

    async def _process_by_intent(self, intent: Intent, text: str) -> dict[str, Any]:
        if intent == Intent.COMMAND:
            return {"intent": intent.value, "response": None, "pass_through": True}
        if intent == Intent.APPROVAL:
            return {"intent": intent.value, "response": None, "pass_through": True}
        if intent == Intent.QUESTION:
            return await self._handle_question(text)
        if intent == Intent.GOAL_REQUEST:
            return await self._handle_goal_request(text)
        if intent == Intent.SYSTEM_ACTION:
            return await self._handle_system_action(text)
        if intent == Intent.FEEDBACK:
            return await self._handle_feedback(text)
        return await self._handle_conversation(text)

    # ── Обработчики ──

    async def _handle_question(self, text: str) -> dict[str, Any]:
        """Отвечает на вопрос с полным доступом к системе."""
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
            f"Вопрос владельца: {text}\n\n"
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
            "response": response or "Не удалось получить ответ. Попробуй переформулировать.",
        }

    async def _handle_system_action(self, text: str) -> dict[str, Any]:
        """Выполняет системное действие по запросу владельца."""
        system_context = self._format_system_context()
        available_actions = self._get_available_actions()

        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
            f"Доступные действия:\n{available_actions}\n\n"
            f"Владелец просит: \"{text}\"\n\n"
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

        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
            f"{skills_context}{owner_prefs}\n\n"
            f"Владелец просит: \"{text}\"\n\n"
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

        system_context = self._format_system_context()
        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=(
                f"{VITO_PERSONALITY}\n\n"
                f"=== СОСТОЯНИЕ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
                f"Владелец оставил отзыв: \"{text}\"\n"
                f"Поблагодари и скажи как учтёшь. Покажи текущие цифры."
            ),
            estimated_tokens=300,
        )

        return {
            "intent": Intent.FEEDBACK.value,
            "response": response or "Спасибо за обратную связь! Учту.",
        }

    async def _handle_conversation(self, text: str) -> dict[str, Any]:
        system_context = self._format_system_context()
        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"=== ПОЛНОЕ СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
            f"История разговора:\n{self._format_context()}\n\n"
            f"Владелец: {text}\n\n"
            f"Ответь как коллега. Используй реальные данные из системы. "
            f"Если владелец спрашивает о расходах/моделях/целях — дай точные цифры."
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=500,
        )

        return {
            "intent": Intent.CONVERSATION.value,
            "response": response or "Привет! Я VITO, твой AI-напарник. Чем могу помочь?",
        }

    # ── Исполнение действий ──

    async def _execute_actions(self, actions: list[dict]) -> str:
        """Выполняет действия, запрошенные LLM."""
        results = []
        for act in actions[:3]:  # max 3 действия за раз
            action_name = act.get("action", "")
            params = act.get("params", {})
            try:
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
            result = await self.agent_registry.dispatch(task_type, **params)
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
            self.goal_engine.fail_goal(goal_id, "Отменено владельцем")
            return f"Цель {goal_id} отменена"

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
        return "\n".join(f"  - {a}" for a in actions) if actions else "(нет действий)"

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
