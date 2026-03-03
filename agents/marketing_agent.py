"""MarketingAgent — Agent 04: стратегия, воронки, рекламные тексты."""

import time

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("marketing_agent", agent="marketing_agent")


class MarketingAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="marketing_agent", description="Маркетинговая стратегия, воронки продаж, рекламные тексты", **kwargs)
        self._cache: dict[str, str] = {}

    @property
    def capabilities(self) -> list[str]:
        return ["marketing_strategy", "funnel"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "marketing_strategy":
                result = await self.create_strategy(kwargs.get("product", ""), kwargs.get("target_audience", ""), kwargs.get("budget_usd", 100))
            elif task_type == "funnel":
                result = await self.design_funnel(kwargs.get("product", kwargs.get("step", "")))
            elif task_type == "ad_copy":
                result = await self.create_ad_copy(kwargs.get("product", ""), kwargs.get("platform", "facebook"))
            else:
                result = await self.create_strategy(kwargs.get("step", task_type), "general", 100)
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_strategy(self, product: str, target_audience: str, budget_usd: float = 100) -> TaskResult:
        key = f"strategy::{(product or '').strip().lower()}::{(target_audience or '').strip().lower()}::{float(budget_usd)}"
        if key in self._cache:
            return TaskResult(success=True, output=self._cache[key], metadata={"cached": True})

        local = self._local_strategy(product, target_audience, budget_usd)
        if not self.llm_router:
            self._cache[key] = local
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})

        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=(
                f"Создай маркетинговую стратегию для продукта: {product}\n"
                f"ЦА: {target_audience}\nБюджет: ${budget_usd}\n"
                "Включи: каналы, тактики, KPI, timeline."
            ),
            estimated_tokens=3000,
        )
        output = response or local
        cost = 0.0
        if response:
            cost = 0.03
            self._record_expense(cost, f"Marketing strategy: {product[:50]}")
        self._cache[key] = output
        return TaskResult(success=True, output=output, cost_usd=cost)

    async def design_funnel(self, product: str, stages: list[str] = None) -> TaskResult:
        local = self._local_funnel(product, stages)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        stages_str = f"Этапы: {', '.join(stages)}" if stages else "Стандартная воронка: awareness → interest → desire → action"
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Спроектируй воронку продаж для: {product}\n{stages_str}\nОпиши каждый этап, контент, метрики.",
            estimated_tokens=2500,
        )
        if not response:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def create_ad_copy(self, product: str, platform: str, style: str = "direct") -> TaskResult:
        local = self._local_ad_copy(product, platform, style)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Напиши рекламный текст для {platform}. Продукт: {product}. Стиль: {style}. 3 варианта.",
            estimated_tokens=1500,
        )
        if not response:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def suggest_channels(self, product: str, budget_usd: float = 100) -> TaskResult:
        local = self._local_channels(product, budget_usd)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Предложи лучшие маркетинговые каналы для: {product}, бюджет ${budget_usd}.",
            estimated_tokens=1500,
        )
        return TaskResult(success=True, output=response or local, cost_usd=0.01 if response else 0.0)

    def _local_strategy(self, product: str, target_audience: str, budget_usd: float) -> str:
        product_name = (product or "Digital product").strip()
        audience = (target_audience or "broad audience").strip()
        budget = max(float(budget_usd or 0), 0.0)
        paid = round(budget * 0.45, 2)
        content = round(budget * 0.35, 2)
        experiments = round(max(budget - paid - content, 0.0), 2)
        return (
            "Marketing strategy (local fallback)\n"
            f"Product: {product_name}\n"
            f"Target audience: {audience}\n"
            f"Budget: ${budget:.2f}\n"
            "Channel mix:\n"
            f"- Paid acquisition: ${paid} (Meta/TikTok search testing)\n"
            f"- Content/SEO: ${content} (landing + short content + lead magnet)\n"
            f"- Experiments: ${experiments} (new angle/A-B tests)\n"
            "KPI:\n"
            "- CTR >= 1.5%\n"
            "- Landing CR >= 2.5%\n"
            "- CAC <= target margin threshold\n"
            "Timeline:\n"
            "- Week 1: message-market fit + baseline creatives\n"
            "- Week 2-3: scale winning channel + add retargeting\n"
            "- Week 4: optimize funnel and cut weak ad sets"
        )

    def _local_funnel(self, product: str, stages: list[str] | None) -> str:
        product_name = (product or "Digital product").strip()
        ordered = stages or ["awareness", "interest", "desire", "action"]
        lines = [f"Funnel for {product_name} (local fallback):"]
        for stage in ordered:
            s = stage.strip().lower()
            if s == "awareness":
                lines.append("- awareness: short videos/posts + lead hook, metric: reach, CTR")
            elif s == "interest":
                lines.append("- interest: demo/value post + email capture, metric: opt-in rate")
            elif s == "desire":
                lines.append("- desire: proof/case study + objections handling, metric: checkout starts")
            elif s == "action":
                lines.append("- action: offer + urgency + simple checkout, metric: conversion rate")
            else:
                lines.append(f"- {s}: define content asset, trigger and success metric")
        return "\n".join(lines)

    def _local_ad_copy(self, product: str, platform: str, style: str) -> str:
        p = (product or "Digital product").strip()
        net = (platform or "social").strip()
        tone = (style or "direct").strip()
        return (
            f"Ad copy for {net} ({tone}, local fallback)\n"
            f"1) Stop wasting time. {p} gives you a ready workflow in minutes.\n"
            f"2) Built for speed: {p} helps you launch faster and cleaner.\n"
            f"3) Get results this week with {p}. Simple setup, immediate value."
        )

    def _local_channels(self, product: str, budget_usd: float) -> str:
        budget = max(float(budget_usd or 0), 0.0)
        if budget < 100:
            profile = "low-budget"
            channels = "SEO long-tail, communities, email capture, creator collabs"
        elif budget < 1000:
            profile = "mid-budget"
            channels = "Meta/TikTok tests, retargeting, SEO cluster pages, newsletter sponsorship"
        else:
            profile = "growth-budget"
            channels = "multi-channel ads, creator network, affiliate program, conversion CRO sprint"
        return (
            f"Channel recommendation (local fallback)\n"
            f"Product: {(product or 'Digital product').strip()}\n"
            f"Budget: ${budget:.2f} ({profile})\n"
            f"Recommended channels: {channels}"
        )
