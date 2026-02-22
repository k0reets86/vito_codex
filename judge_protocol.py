"""Judge Protocol — мультимодельная оценка ниш.

Вызывает 4 модели ПАРАЛЛЕЛЬНО для оценки ниши по 5 критериям.
Каждая модель голосует → агрегированный вердикт.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from config.logger import get_logger
from llm_router import LLMRouter, TaskType, MODEL_REGISTRY

logger = get_logger("judge_protocol", agent="judge_protocol")

# Веса критериев NicheScore
CRITERIA_WEIGHTS = {
    "demand": 0.30,
    "competition": 0.20,
    "margin": 0.20,
    "automation": 0.15,
    "scaling": 0.15,
}

NICHE_THRESHOLD = 65  # Минимальный порог: >65/100


@dataclass
class NicheScore:
    demand: float = 0.0       # 0-100: спрос
    competition: float = 0.0  # 0-100: конкуренция (100 = мало конкуренции, хорошо)
    margin: float = 0.0       # 0-100: маржинальность
    automation: float = 0.0   # 0-100: потенциал автоматизации
    scaling: float = 0.0      # 0-100: масштабируемость

    @property
    def weighted_score(self) -> float:
        return (
            self.demand * CRITERIA_WEIGHTS["demand"]
            + self.competition * CRITERIA_WEIGHTS["competition"]
            + self.margin * CRITERIA_WEIGHTS["margin"]
            + self.automation * CRITERIA_WEIGHTS["automation"]
            + self.scaling * CRITERIA_WEIGHTS["scaling"]
        )

    @property
    def passes_threshold(self) -> bool:
        return self.weighted_score > NICHE_THRESHOLD


@dataclass
class JudgeVote:
    model: str
    score: NicheScore
    reasoning: str = ""
    raw_response: str = ""
    error: Optional[str] = None


@dataclass
class JudgeVerdict:
    niche: str
    votes: list[JudgeVote] = field(default_factory=list)
    avg_score: float = 0.0
    recommendation: str = ""
    approved: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class JudgeProtocol:
    def __init__(self, llm_router: LLMRouter, memory, comms):
        self.llm_router = llm_router
        self.memory = memory
        self.comms = comms
        logger.info("JudgeProtocol инициализирован", extra={"event": "init"})

    async def evaluate_niche(
        self, niche: str, context: dict[str, Any] | None = None
    ) -> JudgeVerdict:
        """Оценивает нишу через 1 экономичную модель (вместо 4 параллельных).

        Стоимость: ~$0.01 вместо $0.20.
        Вызов 4 моделей доступен через evaluate_niche_deep() по запросу владельца.
        """
        logger.info(
            f"Оценка ниши: {niche}",
            extra={"event": "niche_evaluation_start", "context": {"niche": niche}},
        )

        # Одна бесплатная модель для быстрой оценки
        models_to_query = ["gemini-flash"]

        tasks = [
            self._query_model(model_key, niche, context)
            for model_key in models_to_query
        ]
        votes = await asyncio.gather(*tasks, return_exceptions=True)

        # Собираем голоса
        valid_votes: list[JudgeVote] = []
        for v in votes:
            if isinstance(v, JudgeVote) and v.error is None:
                valid_votes.append(v)
            elif isinstance(v, JudgeVote):
                valid_votes.append(v)  # Include with error for reporting

        # Рассчитываем средний балл
        scores = [v.score.weighted_score for v in valid_votes if v.error is None]
        avg_score = sum(scores) / len(scores) if scores else 0

        approved = avg_score > NICHE_THRESHOLD

        recommendation = self._generate_recommendation(niche, avg_score, valid_votes)

        verdict = JudgeVerdict(
            niche=niche,
            votes=valid_votes,
            avg_score=avg_score,
            recommendation=recommendation,
            approved=approved,
        )

        # Сохраняем в память
        if self.memory:
            try:
                self.memory.save_pattern(
                    category="niche_evaluation",
                    key=niche[:100],
                    value=json.dumps({
                        "avg_score": avg_score,
                        "approved": approved,
                        "votes": len(valid_votes),
                    }),
                    confidence=avg_score / 100,
                )
            except Exception:
                pass

        logger.info(
            f"Оценка ниши завершена: {niche} → {avg_score:.1f}/100 ({'одобрена' if approved else 'отклонена'})",
            extra={
                "event": "niche_evaluation_done",
                "context": {"niche": niche, "avg_score": avg_score, "approved": approved},
            },
        )

        return verdict

    async def evaluate_niche_deep(
        self, niche: str, context: dict[str, Any] | None = None
    ) -> JudgeVerdict:
        """Полная оценка ниши через 4 модели параллельно (~$0.20).

        Вызывать только по явному запросу владельца.
        """
        logger.info(
            f"DEEP оценка ниши: {niche}",
            extra={"event": "niche_evaluation_deep_start", "context": {"niche": niche}},
        )

        # Brainstorm: Opus + GPT-4o + Perplexity (мультиперспективный анализ)
        models_to_query = ["claude-opus", "gpt-5", "perplexity"]
        tasks = [
            self._query_model(model_key, niche, context)
            for model_key in models_to_query
        ]
        votes = await asyncio.gather(*tasks, return_exceptions=True)

        valid_votes: list[JudgeVote] = []
        for v in votes:
            if isinstance(v, JudgeVote):
                valid_votes.append(v)

        scores = [v.score.weighted_score for v in valid_votes if v.error is None]
        avg_score = sum(scores) / len(scores) if scores else 0
        approved = avg_score > NICHE_THRESHOLD
        recommendation = self._generate_recommendation(niche, avg_score, valid_votes)

        verdict = JudgeVerdict(
            niche=niche, votes=valid_votes, avg_score=avg_score,
            recommendation=recommendation, approved=approved,
        )

        if self.memory:
            try:
                self.memory.save_pattern(
                    category="niche_evaluation_deep",
                    key=niche[:100],
                    value=json.dumps({"avg_score": avg_score, "approved": approved, "votes": len(valid_votes)}),
                    confidence=avg_score / 100,
                )
            except Exception:
                pass

        return verdict

    async def brainstorm(
        self, topic: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Strategic brainstorm: multi-model role-based discussion.

        Flow (each builds on previous):
          1. Sonnet — CREATES idea/proposal (fast, quality)
          2. Perplexity — RESEARCHES market data, competitors, trends
          3. GPT-5 + Opus + Perplexity — DISCUSS/ARGUE (multi-perspective)
          4. Opus or Sonnet — EXECUTES final strategy

        Cost: ~$0.50-0.80 (6 LLM calls). Use only for important strategic decisions.
        """
        logger.info(
            f"Brainstorm: {topic}",
            extra={"event": "brainstorm_start", "context": {"topic": topic}},
        )

        ctx = json.dumps(context or {}, ensure_ascii=False) if context else ""
        rounds: list[dict[str, str]] = []

        # Round 1: Idea Creator (Sonnet — fast, quality)
        idea = await self._brainstorm_round(
            model_key="claude-sonnet",
            system_role="Ты креативный стратег. Создай сильную идею и начальный план.",
            prompt=(
                f"Предложи стратегию для: {topic}\n"
                f"{f'Контекст: {ctx}' if ctx else ''}\n\n"
                f"Дай конкретный план: 5-7 шагов, сроки, ожидаемые результаты, бюджет. "
                f"Будь креативным но реалистичным."
            ),
        )
        rounds.append({"role": "idea_creator", "model": "claude-sonnet", "content": idea})

        # Round 2: Researcher (Perplexity — web search for real data)
        research = await self._brainstorm_round(
            model_key="perplexity",
            system_role="Ты исследователь рынка. Найди реальные данные для проверки идеи.",
            prompt=(
                f"Тема: {topic}\n\n"
                f"ПРЕДЛОЖЕННАЯ ИДЕЯ:\n{idea[:2000]}\n\n"
                f"Найди реальные данные: размер рынка, конкуренты, цены конкурентов, "
                f"тренды, примеры успеха/провала, целевая аудитория. "
                f"Подтверди или опровергни предположения из идеи."
            ),
        )
        rounds.append({"role": "researcher", "model": "perplexity", "content": research})

        # Round 3a: Discussion — GPT-5 (критик + новые идеи)
        gpt_opinion = await self._brainstorm_round(
            model_key="gpt-5",
            system_role=(
                "Ты опытный бизнес-консультант. Критикуй, дополняй, предлагай альтернативы. "
                "Не соглашайся просто так — спорь если видишь проблемы."
            ),
            prompt=(
                f"Тема: {topic}\n\n"
                f"ИДЕЯ:\n{idea[:1000]}\n\n"
                f"ДАННЫЕ РЫНКА:\n{research[:1000]}\n\n"
                f"Дай свою оценку: что работает, что нет, какие риски, "
                f"что бы ты изменил. Предложи альтернативы если есть."
            ),
        )
        rounds.append({"role": "critic", "model": "gpt-5", "content": gpt_opinion})

        # Round 3b: Discussion — Opus (стратегический взгляд)
        opus_opinion = await self._brainstorm_round(
            model_key="claude-opus",
            system_role=(
                "Ты главный стратег. Ты видишь всё обсуждение и добавляешь глубину. "
                "Не повторяй то что уже сказано — дополняй."
            ),
            prompt=(
                f"Тема: {topic}\n\n"
                f"ИДЕЯ (Sonnet):\n{idea[:600]}\n\n"
                f"ДАННЫЕ РЫНКА (Perplexity):\n{research[:600]}\n\n"
                f"КРИТИКА (GPT-5):\n{gpt_opinion[:600]}\n\n"
                f"Добавь стратегическую глубину: долгосрочные риски, масштабирование, "
                f"что все пропустили, нестандартные подходы."
            ),
        )
        rounds.append({"role": "strategist", "model": "claude-opus", "content": opus_opinion})

        # Round 3c: Discussion — Perplexity (факт-чек дискуссии)
        fact_check = await self._brainstorm_round(
            model_key="perplexity",
            system_role="Проверь утверждения из дискуссии. Подтверди или опровергни фактами.",
            prompt=(
                f"Тема: {topic}\n\n"
                f"ДИСКУССИЯ:\n"
                f"Критик сказал: {gpt_opinion[:500]}\n\n"
                f"Стратег сказал: {opus_opinion[:500]}\n\n"
                f"Проверь ключевые утверждения фактами. Какие данные подтверждают, "
                f"какие опровергают? Добавь новые факты если нашёл."
            ),
        )
        rounds.append({"role": "fact_checker", "model": "perplexity", "content": fact_check})

        # Round 4: Final Strategy (Opus — synthesize everything)
        synthesis = await self._brainstorm_round(
            model_key="claude-opus",
            system_role="Ты финальный стратег. Собери всё в одну чёткую стратегию для реализации.",
            prompt=(
                f"Тема: {topic}\n\n"
                f"ИДЕЯ:\n{idea[:400]}\n\n"
                f"ДАННЫЕ:\n{research[:400]}\n\n"
                f"КРИТИКА:\n{gpt_opinion[:400]}\n\n"
                f"СТРАТЕГИЯ:\n{opus_opinion[:400]}\n\n"
                f"ФАКТЫ:\n{fact_check[:400]}\n\n"
                f"Синтезируй ФИНАЛЬНУЮ стратегию: конкретный план действий, "
                f"приоритеты, сроки, бюджет. Учти все точки зрения."
            ),
        )
        rounds.append({"role": "executor", "model": "claude-opus", "content": synthesis})

        logger.info(
            f"Brainstorm завершён: {topic}",
            extra={"event": "brainstorm_done", "context": {"topic": topic, "rounds": len(rounds)}},
        )

        return {
            "topic": topic,
            "rounds": rounds,
            "final_strategy": synthesis,
        }

    async def _brainstorm_round(
        self, model_key: str, system_role: str, prompt: str
    ) -> str:
        """One round of brainstorm discussion."""
        model = MODEL_REGISTRY.get(model_key)
        if not model:
            return f"[Модель {model_key} не найдена]"

        if not self.llm_router.check_daily_limit():
            return "[Бюджет исчерпан — раунд пропущен]"

        try:
            text, cost = await self.llm_router._call_provider(model, prompt, system_role)
            # Record spend
            self.llm_router._record_spend(
                model.display_name, "strategy_brainstorm", 0, 0, cost
            )
            # Bridge to financial controller
            if self.llm_router._finance and cost > 0:
                try:
                    from financial_controller import ExpenseCategory
                    self.llm_router._finance.record_expense(
                        amount_usd=cost,
                        category=ExpenseCategory.API,
                        agent="judge_brainstorm",
                        description=f"{model.display_name}: brainstorm",
                    )
                except Exception:
                    pass
            return text
        except Exception as e:
            logger.warning(
                f"Brainstorm round error ({model_key}): {e}",
                extra={"event": "brainstorm_round_error"},
            )
            return f"[Ошибка {model_key}: {e}]"

    def format_brainstorm_for_telegram(self, result: dict[str, Any]) -> str:
        """Format brainstorm result for Telegram."""
        role_names = {
            "idea_creator": "Идея (Sonnet)",
            "researcher": "Исследование (Perplexity)",
            "critic": "Критика (GPT-5)",
            "strategist": "Стратегия (Opus)",
            "fact_checker": "Факт-чек (Perplexity)",
            "executor": "Финальная стратегия (Opus)",
        }
        lines = [f"Brainstorm: {result['topic']}", ""]
        for r in result["rounds"]:
            name = role_names.get(r["role"], r["role"])
            content = r["content"][:500] if r["content"] else "[пусто]"
            lines.append(f"--- {name} ({r['model']}) ---")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)

    async def _query_model(
        self, model_key: str, niche: str, context: dict[str, Any] | None
    ) -> JudgeVote:
        """Запрашивает оценку у конкретной модели."""
        model = MODEL_REGISTRY.get(model_key)
        if not model:
            return JudgeVote(model=model_key, score=NicheScore(), error=f"Model {model_key} not found")

        prompt = (
            f"Оцени нишу для цифровых продуктов: \"{niche}\"\n\n"
            f"Дай оценку по 5 критериям (0-100):\n"
            f"1. demand — спрос на рынке\n"
            f"2. competition — низкая конкуренция (100 = мало конкурентов)\n"
            f"3. margin — маржинальность\n"
            f"4. automation — потенциал автоматизации\n"
            f"5. scaling — масштабируемость\n\n"
            f"{'Контекст: ' + json.dumps(context, ensure_ascii=False) if context else ''}\n\n"
            f"Ответь строго в JSON:\n"
            f'{{"demand": 75, "competition": 60, "margin": 80, "automation": 70, "scaling": 65, "reasoning": "объяснение"}}'
        )

        try:
            response_tuple = await self.llm_router._call_provider(model, prompt, "You are a market analysis expert.")
            if not response_tuple:
                return JudgeVote(model=model_key, score=NicheScore(), error="Empty response")

            response = response_tuple[0]  # (text, cost) tuple

            # Parse JSON
            text = response.strip()
            if "```" in text:
                for block in text.split("```"):
                    block = block.strip()
                    if block.startswith("json"):
                        block = block[4:].strip()
                    if block.startswith("{"):
                        text = block
                        break

            data = json.loads(text)
            score = NicheScore(
                demand=float(data.get("demand", 0)),
                competition=float(data.get("competition", 0)),
                margin=float(data.get("margin", 0)),
                automation=float(data.get("automation", 0)),
                scaling=float(data.get("scaling", 0)),
            )
            return JudgeVote(
                model=model_key,
                score=score,
                reasoning=data.get("reasoning", ""),
                raw_response=response[:500],
            )

        except json.JSONDecodeError as e:
            return JudgeVote(model=model_key, score=NicheScore(), error=f"JSON parse error: {e}", raw_response=response[:200] if response else "")
        except Exception as e:
            return JudgeVote(model=model_key, score=NicheScore(), error=str(e))

    def _generate_recommendation(
        self, niche: str, avg_score: float, votes: list[JudgeVote]
    ) -> str:
        """Генерирует текстовую рекомендацию."""
        if avg_score >= 80:
            verdict = "Отличная ниша! Рекомендую начать немедленно."
        elif avg_score >= NICHE_THRESHOLD:
            verdict = "Перспективная ниша. Стоит протестировать."
        elif avg_score >= 50:
            verdict = "Средняя ниша. Нужна дополнительная проверка."
        else:
            verdict = "Слабая ниша. Не рекомендую."

        return f"{niche}: {avg_score:.1f}/100 — {verdict}"

    def format_verdict_for_telegram(self, verdict: JudgeVerdict) -> str:
        """Форматирует вердикт для Telegram."""
        icon = "+" if verdict.approved else "-"
        lines = [
            f"[{icon}] Judge Protocol | {verdict.niche}",
            f"Средний балл: {verdict.avg_score:.1f}/100",
            f"Решение: {'ОДОБРЕНА' if verdict.approved else 'ОТКЛОНЕНА'}",
            "",
            "Голоса моделей:",
        ]
        for vote in verdict.votes:
            if vote.error:
                lines.append(f"  {vote.model}: ОШИБКА ({vote.error[:50]})")
            else:
                lines.append(
                    f"  {vote.model}: {vote.score.weighted_score:.1f}/100"
                    f" (D:{vote.score.demand:.0f} C:{vote.score.competition:.0f}"
                    f" M:{vote.score.margin:.0f} A:{vote.score.automation:.0f}"
                    f" S:{vote.score.scaling:.0f})"
                )
                if vote.reasoning:
                    lines.append(f"    → {vote.reasoning[:100]}")

        lines.append("")
        lines.append(verdict.recommendation)
        return "\n".join(lines)
