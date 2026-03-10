from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from modules.owner_model import OwnerModel
from modules.reflector import VITOReflector


class OpportunityScout(BaseAgent):
    NEEDS = {
        "scan_opportunities": ["trend_sources", "owner_model", "reflector"],
        "propose_opportunities": ["trend_sources", "owner_model"],
        "*": ["trend_sources"],
    }

    def __init__(self, **kwargs):
        super().__init__(name="opportunity_scout", description="Проактивный сканер рыночных возможностей", **kwargs)
        self.owner_model = OwnerModel()
        self.reflector = VITOReflector()

    @property
    def capabilities(self) -> list[str]:
        return ["scan_opportunities", "propose_opportunities"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        try:
            proposals = await self.scan_and_propose()
            return TaskResult(success=True, output=proposals)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def scan_and_propose(self) -> dict[str, Any]:
        trend_result = await self.ask("trend_scan", silent=True, keywords=["digital products", "creator economy", "memes"])
        research_result = await self.ask("research", silent=True, topic="digital product trends and low competition opportunities")
        success_patterns = self.reflector.get_recent(n=5, category="ecommerce")
        prefs = self.owner_model.get_preferences()
        proposals = self._build_proposals(trend_result, research_result, success_patterns, prefs)
        filtered = self.owner_model.filter_goals(proposals)
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "proposals": filtered[:3]}

    def _build_proposals(self, trend_result, research_result, success_patterns: list[str], prefs: dict[str, Any]) -> list[dict[str, Any]]:
        trend_text = str(getattr(trend_result, "output", "") or "")[:1500]
        research_text = str(getattr(research_result, "output", "") or "")[:1500]
        lower = f"{trend_text}\n{research_text}".lower()
        meme_bias = 1 if "meme" in lower else 0
        return [
            {
                "title": "Creator playbook product around fast-moving meme trends" if meme_bias else "Digital playbook for creators in a trending niche",
                "rationale": "Trend data + research suggest opportunity in fast reaction digital products.",
                "expected_revenue": 180 + 40 * meme_bias,
                "effort": "medium",
                "type": "create",
                "confidence": 0.76,
            },
            {
                "title": "Low-ticket template bundle for Etsy/Gumroad",
                "rationale": "Fast-to-launch bundle with broad buyer intent and low production cost.",
                "expected_revenue": 140,
                "effort": "low",
                "type": "create",
                "confidence": 0.71,
            },
            {
                "title": "Platform optimization sprint for weakest commerce flow",
                "rationale": "Execution friction is directly reducing revenue throughput.",
                "expected_revenue": 120,
                "effort": "medium",
                "type": "optimize",
                "confidence": 0.67,
            },
        ]
