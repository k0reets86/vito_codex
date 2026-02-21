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
        """Оценивает нишу через 4 модели параллельно."""
        logger.info(
            f"Оценка ниши: {niche}",
            extra={"event": "niche_evaluation_start", "context": {"niche": niche}},
        )

        # Модели для оценки
        models_to_query = ["claude-opus", "gpt-o3", "perplexity", "claude-sonnet"]

        # Параллельные запросы
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
            response = await self.llm_router._call_provider(model, prompt, "You are a market analysis expert.")
            if not response:
                return JudgeVote(model=model_key, score=NicheScore(), error="Empty response")

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
