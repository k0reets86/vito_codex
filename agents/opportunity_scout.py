from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from llm_router import TaskType
from modules.owner_model import OwnerModel
from modules.reflector import VITOReflector
from modules.skill_library import VITOSkillLibrary


class OpportunityScout(BaseAgent):
    NEEDS = {
        "scan_opportunities": ["trend_sources", "owner_model", "reflector"],
        "propose_opportunities": ["trend_sources", "owner_model"],
        "*": ["trend_sources"],
    }

    def __init__(self, **kwargs):
        super().__init__(name="opportunity_scout", description="Проактивный сканер рыночных возможностей", **kwargs)
        self.owner_model = OwnerModel()
        self.reflector = VITOReflector(memory_manager=self.memory)
        self.skill_lib = VITOSkillLibrary()

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
        skill_query = f"{getattr(trend_result, 'output', '')} {getattr(research_result, 'output', '')}".strip() or "digital products opportunities"
        related_skills = self.skill_lib.retrieve(skill_query, n=5)
        proposals = await self._build_proposals(trend_result, research_result, success_patterns, prefs, related_skills)
        filtered = self.owner_model.filter_goals(proposals)
        used_skills = [str(item.get("name") or "").strip() for item in related_skills if str(item.get("name") or "").strip()]
        for skill_name in used_skills[:5]:
            try:
                self.skill_lib.record_use(skill_name, success=True)
            except Exception:
                pass
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "proposals": filtered[:3],
            "used_skills": used_skills[:5],
            "runtime_profile": {
                "trend_signal_present": bool(str(getattr(trend_result, "output", "") or "").strip()),
                "research_signal_present": bool(str(getattr(research_result, "output", "") or "").strip()),
                "skill_support": used_skills[:5],
                "owner_risk": str(prefs.get("risk_appetite") or "medium"),
            },
        }

    @staticmethod
    def _extract_json_list(raw: str) -> list[dict[str, Any]]:
        text = str(raw or "").strip()
        if not text:
            return []
        candidates = [text]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidates.insert(0, text[start : end + 1])
        for chunk in candidates:
            try:
                data = json.loads(chunk)
            except Exception:
                continue
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        return []

    async def _build_proposals(self, trend_result, research_result, success_patterns: list[str], prefs: dict[str, Any], related_skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trend_text = str(getattr(trend_result, "output", "") or "")[:1500]
        research_text = str(getattr(research_result, "output", "") or "")[:1500]
        prompt = (
            "You are VITO OpportunityScout. Generate realistic market opportunities as JSON.\n"
            "Return only a JSON array with up to 5 objects.\n"
            "Schema: [{\"title\": str, \"rationale\": str, \"expected_revenue\": number, "
            "\"effort\": \"low\"|\"medium\"|\"high\", \"type\": \"create\"|\"optimize\"|\"expand\", "
            "\"confidence\": number}]\n\n"
            f"TREND DATA:\n{trend_text[:1200]}\n\n"
            f"RESEARCH DATA:\n{research_text[:1200]}\n\n"
            f"SUCCESS PATTERNS:\n{json.dumps(success_patterns[:3], ensure_ascii=False)}\n\n"
            f"RELEVANT SKILLS:\n{json.dumps([{'name': s.get('name'), 'description': s.get('description')} for s in related_skills[:5]], ensure_ascii=False)}\n\n"
            f"OWNER PREFERENCES:\n{json.dumps(prefs, ensure_ascii=False)}\n\n"
            "Generate personalized opportunities for monetization and execution."
        )
        try:
            reply = await self._call_llm(task_type=TaskType.RESEARCH, prompt=prompt)
            parsed = self._extract_json_list(reply)
            if parsed:
                normalized: list[dict[str, Any]] = []
                for item in parsed[:5]:
                    normalized.append(
                        {
                            "title": str(item.get("title", "")).strip()[:160],
                            "rationale": str(item.get("rationale", "")).strip()[:800],
                            "expected_revenue": float(item.get("expected_revenue", 0) or 0),
                            "effort": str(item.get("effort", "medium")).strip().lower() or "medium",
                            "type": str(item.get("type", "create")).strip().lower() or "create",
                            "confidence": float(item.get("confidence", 0.65) or 0.65),
                        }
                    )
                if normalized:
                    return normalized
        except Exception:
            pass
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
