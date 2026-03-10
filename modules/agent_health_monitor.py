from __future__ import annotations

from typing import Any, Optional

from config.settings import settings
from modules.agent_feedback import AgentFeedback
from modules.data_lake import DataLake
from modules.failure_substrate import build_failure_substrate


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class AgentHealthMonitor:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._lake = DataLake(sqlite_path=self.sqlite_path)
        self._feedback = AgentFeedback(sqlite_path=self.sqlite_path)

    def build_report(self, days: int = 30, limit: int = 50) -> dict[str, Any]:
        stats = list(self._lake.agent_stats(days=days) or [])
        feedback_rows = list(self._feedback.recent(limit=max(limit, 100)) or [])
        rows: list[dict[str, Any]] = []
        by_agent_feedback: dict[str, list[dict[str, Any]]] = {}

        for row in feedback_rows:
            agent = str(row.get("agent") or "").strip()
            if agent:
                by_agent_feedback.setdefault(agent, []).append(row)

        for stat in stats:
            agent = str(stat.get("agent") or "").strip()
            recent_feedback = by_agent_feedback.get(agent, [])
            recent_failures = list(
                (build_failure_substrate(agent=agent, limit=max(limit, 50), sqlite_path=self.sqlite_path) or {}).get("entries")
                or []
            )
            success_rate = float(stat.get("success_rate") or 0.0)
            total = int(stat.get("total") or 0)
            fail_count = int(stat.get("fail") or 0)
            feedback_success = (
                sum(1 for item in recent_feedback if bool(item.get("success"))) / len(recent_feedback)
                if recent_feedback
                else success_rate
            )
            failure_pressure = min(1.0, len(recent_failures) / max(1.0, float(limit)))
            health_score = round(
                (
                    _clamp01(success_rate) * 0.45
                    + _clamp01(feedback_success) * 0.25
                    + _clamp01(min(total / 20.0, 1.0)) * 0.10
                    + (1.0 - _clamp01(failure_pressure)) * 0.20
                )
                * 10.0,
                2,
            )
            rows.append(
                {
                    "agent": agent,
                    "total": total,
                    "success_rate": round(success_rate, 4),
                    "feedback_success_rate": round(feedback_success, 4),
                    "recent_failure_count": len(recent_failures),
                    "health_score": health_score,
                    "state": self._classify(health_score, fail_count=fail_count),
                }
            )

        rows.sort(key=lambda item: (item.get("health_score", 0.0), item.get("total", 0)), reverse=True)
        return {
            "days": days,
            "agents": rows,
            "agent_count": len(rows),
            "avg_health_score": round(sum(float(r["health_score"]) for r in rows) / len(rows), 2) if rows else 0.0,
        }

    @staticmethod
    def _classify(score: float, *, fail_count: int = 0) -> str:
        if score < 4.5 or fail_count >= 8:
            return "critical"
        if score < 6.5 or fail_count >= 4:
            return "degraded"
        return "healthy"
