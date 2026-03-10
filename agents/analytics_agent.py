"""AnalyticsAgent — Agent 09: ежедневный дашборд, аномалии, прогнозы."""

import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.research_family_runtime import build_analytics_runtime_profile

logger = get_logger("analytics_agent", agent="analytics_agent")


class AnalyticsAgent(BaseAgent):
    NEEDS = {
        "dashboard": ["health_check"],
        "anomalies": ["analytics"],
        "forecast": ["pricing"],
        "agent_performance": ["agent_improvement"],
        "default": [],
    }

    def __init__(self, registry=None, **kwargs):
        super().__init__(name="analytics_agent", description="Аналитика: дашборд, аномалии, прогнозы, ROI", **kwargs)
        self.registry = registry

    @property
    def capabilities(self) -> list[str]:
        return ["analytics", "dashboard", "forecast", "anomalies"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "dashboard":
                result = await self.daily_dashboard()
            elif task_type == "anomalies":
                result = await self.detect_anomalies()
            elif task_type == "forecast":
                result = await self.forecast_revenue(kwargs.get("days", 30))
            elif task_type == "agent_performance":
                result = await self.agent_performance()
            else:
                result = await self.daily_dashboard()
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def daily_dashboard(self) -> TaskResult:
        spend = 0.0
        revenue = 0.0
        if self.finance:
            try:
                spend = float(self.finance.get_daily_spend())
            except Exception:
                spend = 0.0
            try:
                revenue = float(self.finance.get_daily_revenue())
            except Exception:
                revenue = 0.0
        profit = round(revenue - spend, 2)
        data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            "daily_spend": round(spend, 2),
            "daily_revenue": round(revenue, 2),
            "daily_profit": profit,
            "roi_percent": round((profit / spend) * 100, 2) if spend > 0 else None,
            "health": "ok" if profit >= 0 else "watch",
        }
        data["evidence"] = {
            "has_spend": spend > 0,
            "has_revenue": revenue > 0,
            "profit_sign": "positive" if profit >= 0 else "negative",
        }
        return TaskResult(
            success=True,
            output=data,
            metadata={
                "analytics_runtime_profile": build_analytics_runtime_profile(
                    anomalies=[],
                    health=data.get("health"),
                    forecast_confidence=None,
                ),
                "analytics_handoff_targets": ["marketing_agent", "ecommerce_agent"] if data.get("health") == "watch" else ["analytics_agent"],
                **self.get_skill_pack(),
            },
        )

    async def detect_anomalies(self) -> TaskResult:
        local = await self._local_anomaly_snapshot()
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.ROUTINE,
            prompt=f"Проанализируй метрики и найди аномалии:\n{local}\nОтветь кратко: есть ли отклонения?",
            estimated_tokens=500,
        )
        if response:
            local["llm_notes"] = response
        return TaskResult(
            success=True,
            output=local,
            metadata={
                "analytics_runtime_profile": build_analytics_runtime_profile(
                    anomalies=local.get("anomalies"),
                    health=local.get("status"),
                    forecast_confidence=None,
                ),
                "analytics_handoff_targets": ["marketing_agent", "ecommerce_agent"] if local.get("anomalies") else ["analytics_agent"],
                **self.get_skill_pack(),
            },
        )

    async def forecast_revenue(self, days: int = 30) -> TaskResult:
        local = await self._local_forecast(days)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Спрогнозируй выручку на {days} дней. Учти текущие тренды. Дай оценку в USD.",
            estimated_tokens=1000,
        )
        if response:
            self._record_expense(0.01, f"Forecast {days}d")
            local["llm_notes"] = response
        return TaskResult(
            success=True,
            output=local,
            cost_usd=0.01 if response else 0.0,
            metadata={
                "analytics_runtime_profile": build_analytics_runtime_profile(
                    anomalies=[],
                    health="forecast",
                    forecast_confidence=local.get("confidence"),
                ),
                "analytics_handoff_targets": ["economics_agent", "marketing_agent"],
                **self.get_skill_pack(),
            },
        )

    async def agent_performance(self) -> TaskResult:
        registry = self.registry or self._registry
        if not registry:
            return TaskResult(success=True, output={"status": "no_registry_attached"})
        statuses = registry.get_all_statuses()
        summary = [
            {
                "name": s.get("name"),
                "completed": s.get("tasks_completed", 0),
                "failed": s.get("tasks_failed", 0),
                "cost_usd": s.get("total_cost", 0),
                "status": s.get("status"),
            }
            for s in statuses
        ]
        weakest = sorted(summary, key=lambda row: row.get("failed", 0), reverse=True)
        strongest = sorted(summary, key=lambda row: row.get("completed", 0), reverse=True)
        return TaskResult(
            success=True,
            output={"agents": summary, "agent_count": len(summary)},
            metadata={
                "analytics_runtime_profile": build_analytics_runtime_profile(
                    anomalies=[],
                    health="agent_performance",
                    forecast_confidence=None,
                ),
                "analytics_handoff_targets": ["hr_agent", "vito_core"],
                "benchmark_snapshot": {"weakest": weakest[:5], "strongest": strongest[:5]},
                **self.get_skill_pack(),
            },
        )

    async def _local_anomaly_snapshot(self) -> dict[str, Any]:
        dashboard = await self.daily_dashboard()
        data = dict(dashboard.output or {})
        spend = float(data.get("daily_spend") or 0.0)
        revenue = float(data.get("daily_revenue") or 0.0)
        anomalies = []
        if spend > 0 and revenue == 0:
            anomalies.append("spend_without_revenue")
        if spend > revenue and revenue > 0:
            anomalies.append("negative_margin_day")
        return {
            "metrics": data,
            "anomalies": anomalies,
            "status": "ok" if not anomalies else "review_required",
            "investigation_plan": ["continue_monitoring"] if not anomalies else ["compare_channel_spend", "check_platform_publish_health", "review_offer_conversion"],
        }

    async def _local_forecast(self, days: int) -> dict[str, Any]:
        dashboard = await self.daily_dashboard()
        daily_revenue = float((dashboard.output or {}).get("daily_revenue") or 0.0)
        baseline = daily_revenue if daily_revenue > 0 else 25.0
        return {
            "days": int(days),
            "baseline_daily_revenue": baseline,
            "forecast_revenue": round(baseline * int(days), 2),
            "confidence": "low" if daily_revenue == 0 else "medium",
        }
