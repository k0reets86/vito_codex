"""EconomicsAgent — Agent 16: ценообразование, юнит-экономика, P&L."""

import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.economics_runtime import build_market_signal_pack, build_pricing_confidence
from modules.weak_agent_runtime import economics_recovery_hints

logger = get_logger("economics_agent", agent="economics_agent")


class EconomicsAgent(BaseAgent):
    NEEDS = {
        "pricing": ["analytics", "marketing_strategy"],
        "unit_economics": ["analytics"],
        "pnl": ["analytics"],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="economics_agent", description="Экономика: ценообразование, юнит-экономика, P&L моделирование", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["pricing", "unit_economics", "pnl"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "pricing":
                result = await self.suggest_price(kwargs.get("product", kwargs.get("step", "")))
            elif task_type == "unit_economics":
                result = await self.unit_economics(kwargs.get("product", kwargs.get("step", "")))
            elif task_type == "pnl":
                result = await self.model_pnl(kwargs.get("scenario", {}))
            else:
                result = await self.suggest_price(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def suggest_price(self, product: str) -> TaskResult:
        local = self._local_price_recommendation(product)
        market_signal = build_market_signal_pack(product)
        confidence = build_pricing_confidence(product)
        local["market_signal_pack"] = market_signal
        local["pricing_confidence"] = confidence
        local["recommendation_rationale"] = (
            f"Recommended {local['recommended_tier']} based on competitor anchors, low variable costs, "
            f"and confidence score {confidence.get('confidence_score', 0):.2f}."
        )
        local["recovery_hints"] = economics_recovery_hints(local)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", **self.get_skill_pack()})
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Предложи оптимальную цену для продукта: {product}\nУчти: конкурентов, ценность, целевую аудиторию, маржу.\nДай 3 варианта: economy, standard, premium.",
            estimated_tokens=1500,
        )
        if response:
            self._record_expense(0.01, f"Pricing: {product[:50]}")
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.01 if response else 0.0, metadata=self.get_skill_pack())

    async def unit_economics(self, product: str) -> TaskResult:
        local = self._local_unit_economics(product)
        local["market_signal_pack"] = build_market_signal_pack(product)
        local["pricing_confidence"] = build_pricing_confidence(product)
        local["recommendation_rationale"] = "Unit economics derived from standard price tier, fees, and blended CAC assumptions."
        local["recovery_hints"] = economics_recovery_hints(local)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", **self.get_skill_pack()})
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Рассчитай юнит-экономику для: {product}\nВключи: CAC, LTV, margin, breakeven point, payback period.",
            estimated_tokens=1500,
        )
        if response:
            self._record_expense(0.01, f"Unit economics: {product[:50]}")
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.01 if response else 0.0, metadata=self.get_skill_pack())

    async def model_pnl(self, scenario: dict) -> TaskResult:
        local = self._local_pnl(scenario)
        local["pricing_confidence"] = build_pricing_confidence(str(scenario.get("product") or "Digital product"), scenario)
        local["recommendation_rationale"] = "P&L projection uses provided scenario inputs with conservative fixed and variable cost assumptions."
        local["recovery_hints"] = economics_recovery_hints(local.get("monthly") or {})
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", **self.get_skill_pack()})
        scenario_text = "\n".join(f"{k}: {v}" for k, v in scenario.items())
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Смоделируй P&L для сценария:\n{scenario_text}\nДай прогноз: выручка, расходы, прибыль, ROI на 3/6/12 месяцев.",
            estimated_tokens=2000,
        )
        if response:
            self._record_expense(0.02, "P&L modeling")
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.02 if response else 0.0, metadata=self.get_skill_pack())

    def _local_price_recommendation(self, product: str) -> dict[str, Any]:
        name = (product or "Digital product").strip() or "Digital product"
        low = 9.0
        if any(x in name.lower() for x in ("bundle", "toolkit", "kit", "journal", "planner")):
            low = 11.0
        if any(x in name.lower() for x in ("course", "masterclass", "system")):
            low = 19.0
        standard = round(low * 1.6, 2)
        premium = round(low * 2.4, 2)
        return {
            "product": name,
            "pricing_options": {
                "economy": round(low, 2),
                "standard": standard,
                "premium": premium,
            },
            "recommended_tier": "standard",
            "margin_logic": "Digital goods have low delivery cost; optimize around perceived transformation and refund risk.",
            "assumptions": ["digital product", "low variable cost", "single-order purchase"],
        }

    def _local_unit_economics(self, product: str) -> dict[str, Any]:
        pricing = self._local_price_recommendation(product)
        price = float(pricing["pricing_options"]["standard"])
        fees = round(max(price * 0.1, 1.5), 2)
        cac = round(max(price * 0.3, 3.0), 2)
        contribution = round(price - fees - cac, 2)
        ltv = round(price * 1.35, 2)
        return {
            "product": (product or "Digital product").strip(),
            "price_point": price,
            "estimated_fees": fees,
            "estimated_cac": cac,
            "estimated_ltv": ltv,
            "contribution_margin": contribution,
            "breakeven_units_1000usd_fixed_cost": 0 if contribution <= 0 else max(int(1000 / contribution), 1),
            "payback_window": "first purchase" if contribution > 0 else "not_profitable",
        }

    def _local_pnl(self, scenario: dict[str, Any]) -> dict[str, Any]:
        price = float(scenario.get("price") or 15)
        units = int(scenario.get("units") or 100)
        fixed_costs = float(scenario.get("fixed_costs") or 250)
        variable_cost_rate = float(scenario.get("variable_cost_rate") or 0.12)
        revenue = round(price * units, 2)
        variable_costs = round(revenue * variable_cost_rate, 2)
        profit = round(revenue - variable_costs - fixed_costs, 2)
        roi = round((profit / fixed_costs) * 100, 2) if fixed_costs > 0 else None
        return {
            "scenario": dict(scenario or {}),
            "monthly": {
                "revenue": revenue,
                "variable_costs": variable_costs,
                "fixed_costs": fixed_costs,
                "profit": profit,
                "roi_percent": roi,
            },
            "projection": {
                "3_month_profit": round(profit * 3, 2),
                "6_month_profit": round(profit * 6, 2),
                "12_month_profit": round(profit * 12, 2),
            },
        }
