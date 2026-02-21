"""ConversationEngine — живой разговор с владельцем.

Утилита (не агент), инжектится в CommsAgent.
Двухступенчатый intent detection: rule-based → LLM.
Хранит контекст последних 20 реплик.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from config.logger import get_logger
from llm_router import LLMRouter, TaskType

logger = get_logger("conversation_engine", agent="conversation_engine")

VITO_PERSONALITY = (
    "Ты VITO — автономный AI-агент, коллега и напарник. "
    "Отвечай на русском. Будь конкретным, давай данные, будь проактивным. "
    "Делись находками, задавай уточняющие вопросы, предлагай следующие шаги. "
    "Тон: дружелюбный, деловой, без лишней воды."
)

MAX_CONTEXT_TURNS = 20


class Intent(Enum):
    COMMAND = "command"
    APPROVAL = "approval"
    QUESTION = "question"
    GOAL_REQUEST = "goal_request"
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
                 finance=None, agent_registry=None, decision_loop=None):
        self.llm_router = llm_router
        self.memory = memory
        self.goal_engine = goal_engine
        self.finance = finance
        self.agent_registry = agent_registry
        self.decision_loop = decision_loop
        self._context: list[Turn] = []
        logger.info("ConversationEngine инициализирован", extra={"event": "init"})

    async def process_message(self, text: str) -> dict[str, Any]:
        """Обрабатывает сообщение от владельца.

        Returns:
            dict: {intent, response, create_goal (optional), goal_title (optional)}
        """
        # 1. Detect intent
        intent = self._detect_intent_rules(text)
        if intent is None:
            intent = await self._detect_intent_llm(text)

        # 2. Save user turn
        self._add_turn("user", text, intent)

        # 3. Process by intent
        result = await self._process_by_intent(intent, text)

        # 4. Save assistant turn
        if result.get("response"):
            self._add_turn("assistant", result["response"])

        return result

    def _detect_intent_rules(self, text: str) -> Optional[Intent]:
        """Rule-based intent detection (быстрый первый фильтр)."""
        stripped = text.strip()

        # Команды начинаются с /
        if stripped.startswith("/"):
            return Intent.COMMAND

        # Одобрение / отклонение
        lower = stripped.lower()
        approval_words = {"да", "нет", "ок", "ok", "yes", "no", "approve", "reject", "отмена", "одобряю", "отклоняю"}
        if lower in approval_words:
            return Intent.APPROVAL

        return None

    async def _detect_intent_llm(self, text: str) -> Intent:
        """LLM-based intent detection через Haiku (~50 токенов)."""
        prompt = (
            f"Определи intent сообщения пользователя. Ответь ОДНИМ словом:\n"
            f"QUESTION — вопрос о системе, данных, статусе\n"
            f"GOAL_REQUEST — просьба сделать что-то, задача, цель\n"
            f"FEEDBACK — отзыв, благодарность, критика\n"
            f"CONVERSATION — свободный разговор, приветствие, шутка\n\n"
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
                    "FEEDBACK": Intent.FEEDBACK,
                    "CONVERSATION": Intent.CONVERSATION,
                }
                return intent_map.get(intent_str, Intent.CONVERSATION)
        except Exception as e:
            logger.debug(f"LLM intent detection failed: {e}", extra={"event": "intent_llm_error"})

        return Intent.CONVERSATION

    async def _process_by_intent(self, intent: Intent, text: str) -> dict[str, Any]:
        """Обработка сообщения по интенту."""
        if intent == Intent.COMMAND:
            return {"intent": intent.value, "response": None, "pass_through": True}

        if intent == Intent.APPROVAL:
            return {"intent": intent.value, "response": None, "pass_through": True}

        if intent == Intent.QUESTION:
            return await self._handle_question(text)

        if intent == Intent.GOAL_REQUEST:
            return await self._handle_goal_request(text)

        if intent == Intent.FEEDBACK:
            return await self._handle_feedback(text)

        # CONVERSATION
        return await self._handle_conversation(text)

    async def _handle_question(self, text: str) -> dict[str, Any]:
        """Отвечает на вопрос с поиском в памяти."""
        # Поиск в памяти
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

        system_context = self._format_system_context()
        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"Текущее состояние системы VITO:\n{system_context}\n\n"
            f"История разговора:\n{self._format_context()}\n\n"
            f"{context_from_memory}\n\n"
            f"Вопрос владельца: {text}\n\n"
            f"Дай конкретный ответ с реальными данными из системы."
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=500,
        )

        return {
            "intent": Intent.QUESTION.value,
            "response": response or "Не удалось получить ответ. Попробуй переформулировать.",
        }

    async def _handle_goal_request(self, text: str) -> dict[str, Any]:
        """Извлекает цель и подтверждает естественным языком."""
        system_context = self._format_system_context()
        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"Текущее состояние системы VITO:\n{system_context}\n\n"
            f"Владелец просит выполнить задачу: \"{text}\"\n\n"
            f"1. Сформулируй краткое название цели (до 100 символов)\n"
            f"2. Напиши подтверждение естественным языком (учитывай существующие цели и бюджет)\n\n"
            f"Ответь в JSON: {{\"goal_title\": \"...\", \"confirmation\": \"...\"}}"
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=300,
        )

        goal_title = text[:100]
        confirmation = f"Принял! Создаю цель: \"{goal_title}\""

        if response:
            try:
                parsed = response.strip()
                if "```" in parsed:
                    for block in parsed.split("```"):
                        block = block.strip()
                        if block.startswith("json"):
                            block = block[4:].strip()
                        if block.startswith("{"):
                            parsed = block
                            break
                if parsed.startswith("{"):
                    data = json.loads(parsed)
                    goal_title = data.get("goal_title", goal_title)
                    confirmation = data.get("confirmation", confirmation)
            except (json.JSONDecodeError, Exception):
                pass

        return {
            "intent": Intent.GOAL_REQUEST.value,
            "response": confirmation,
            "create_goal": True,
            "goal_title": goal_title,
            "goal_description": text,
        }

    async def _handle_feedback(self, text: str) -> dict[str, Any]:
        """Сохраняет фидбек как паттерн."""
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
                f"Поблагодари и скажи как учтёшь."
            ),
            estimated_tokens=200,
        )

        return {
            "intent": Intent.FEEDBACK.value,
            "response": response or "Спасибо за обратную связь! Учту.",
        }

    async def _handle_conversation(self, text: str) -> dict[str, Any]:
        """Свободный разговор с личностью VITO."""
        system_context = self._format_system_context()
        prompt = (
            f"{VITO_PERSONALITY}\n\n"
            f"Текущее состояние системы VITO:\n{system_context}\n\n"
            f"История разговора:\n{self._format_context()}\n\n"
            f"Владелец: {text}\n\n"
            f"Ответь естественно, как коллега. Используй реальные данные из системы."
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=300,
        )

        return {
            "intent": Intent.CONVERSATION.value,
            "response": response or "Привет! Я VITO, твой AI-напарник. Чем могу помочь?",
        }

    def _add_turn(self, role: str, text: str, intent: Optional[Intent] = None) -> None:
        """Добавляет реплику в контекст."""
        self._context.append(Turn(role=role, text=text, intent=intent))
        # Ограничиваем историю
        if len(self._context) > MAX_CONTEXT_TURNS:
            self._context = self._context[-MAX_CONTEXT_TURNS:]

    def _format_system_context(self) -> str:
        """Полный контекст системы: расходы, модели, цели, агенты."""
        parts = []

        # 1. Расходы по моделям (из spend_log)
        try:
            daily_spend = self.llm_router.get_daily_spend()
            breakdown = self.llm_router.get_spend_breakdown(days=1)
            from config.settings import settings as _s
            spend_lines = [f"Расходы LLM сегодня: ${daily_spend:.4f} / ${_s.DAILY_LIMIT_USD:.2f}"]
            if breakdown:
                for row in breakdown:
                    spend_lines.append(
                        f"  {row['model']} [{row['task_type']}]: ${row['total_cost']:.4f} ({row['calls']} вызовов)"
                    )
            parts.append("\n".join(spend_lines))
        except Exception:
            pass

        # 2. Финансы (если подключены)
        if self.finance:
            try:
                daily_spent = self.finance.get_daily_spent()
                daily_earned = self.finance.get_daily_earned()
                by_agent = self.finance.get_spend_by_agent(days=1)
                fin_lines = [f"Финансы: потрачено ${daily_spent:.4f}, заработано ${daily_earned:.2f}"]
                if by_agent:
                    for a in by_agent[:5]:
                        fin_lines.append(f"  {a['agent']}: ${a['total']:.4f} ({a['calls']} операций)")
                parts.append("\n".join(fin_lines))
            except Exception:
                pass

        # 3. Активные цели
        goals_ctx = self._format_goals_context()
        if goals_ctx:
            parts.append(goals_ctx)

        # 4. Статус агентов
        if self.agent_registry:
            try:
                statuses = self.agent_registry.get_all_statuses()
                running = [s for s in statuses if s.get("status") == "running"]
                if running:
                    agent_lines = ["Агенты в работе:"]
                    for s in running[:5]:
                        agent_lines.append(f"  {s['name']}: {s['status']} (задач: {s.get('tasks_completed', 0)})")
                    parts.append("\n".join(agent_lines))
            except Exception:
                pass

        # 5. Decision Loop
        if self.decision_loop:
            try:
                dl_status = self.decision_loop.get_status()
                parts.append(
                    f"Decision Loop: {'работает' if dl_status['running'] else 'остановлен'}, "
                    f"тиков: {dl_status['tick_count']}"
                )
            except Exception:
                pass

        return "\n\n".join(parts) if parts else ""

    def _format_goals_context(self) -> str:
        """Форматирует активные цели для включения в промпт."""
        if not self.goal_engine:
            return ""
        try:
            goals = self.goal_engine.get_all_goals()
            if not goals:
                return ""
            active = [g for g in goals if g.status.value not in ("completed", "failed", "cancelled")]
            if not active:
                return ""
            lines = ["Активные цели VITO:"]
            for g in active[:10]:
                lines.append(f"- [{g.status.value}] {g.title} (приоритет: {g.priority.name}, ${g.estimated_cost_usd:.2f})")
            return "\n".join(lines)
        except Exception:
            return ""

    def _format_context(self) -> str:
        """Форматирует контекст для промпта."""
        if not self._context:
            return "(начало разговора)"
        lines = []
        for turn in self._context[-10:]:  # Последние 10 реплик для промпта
            role_label = "Владелец" if turn.role == "user" else "VITO"
            lines.append(f"{role_label}: {turn.text[:200]}")
        return "\n".join(lines)

    def get_context(self) -> list[dict]:
        """Возвращает контекст для отладки."""
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
        """Очищает контекст разговора."""
        self._context.clear()
