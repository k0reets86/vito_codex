
from __future__ import annotations

from typing import Any
import json

from agents.base_agent import BaseAgent, TaskResult
from modules.apply_engine import ApplyEngine
from modules.autonomy_runtime import build_self_evolve_runtime_profile
from modules.evolution_archive import EvolutionArchive
from modules.evolution_events import EvolutionEventStore
from modules.module_discovery import ModuleDiscovery
from modules.owner_model import OwnerModel
from modules.sandbox_manager import SandboxManager
from modules.skill_library import VITOSkillLibrary
from modules.vito_benchmarks import VITOBenchmarks
from llm_router import TaskType


class SelfEvolverV2(BaseAgent):
    NEEDS = {
        'propose_and_benchmark': ['quality_judge', 'reflector', 'skill_library'],
        '*': ['reflector'],
    }

    def __init__(self, *, sandbox_manager: SandboxManager, apply_engine: ApplyEngine, benchmarks: VITOBenchmarks, discovery: ModuleDiscovery, reflector=None, archive: EvolutionArchive | None = None, event_store: EvolutionEventStore | None = None, **kwargs):
        super().__init__(name='self_evolver_v2', description='Benchmark-driven self-evolution engine', **kwargs)
        self.sandbox_manager = sandbox_manager
        self.apply_engine = apply_engine
        self.benchmarks = benchmarks
        self.discovery = discovery
        self.reflector = reflector
        self.archive = archive or EvolutionArchive()
        self.skill_lib = VITOSkillLibrary()
        self.event_store = event_store or EvolutionEventStore()
        self.owner_model = OwnerModel()

    @property
    def capabilities(self) -> list[str]:
        return ['propose_and_benchmark', 'discover_modules', 'weekly_evolve_cycle']

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        try:
            if task_type == 'discover_modules':
                output = self.discovery.discover(str(kwargs.get('query') or ''), limit=int(kwargs.get('limit', 5) or 5))
                return TaskResult(success=True, output=output)
            if task_type == 'propose_and_benchmark':
                output = await self.propose_and_benchmark(
                    candidates=list(kwargs.get('candidates') or []),
                    baseline_score=float(kwargs.get('baseline_score', 0.0) or 0.0),
                )
                return TaskResult(success=True, output=output)
            if task_type == 'weekly_evolve_cycle':
                output = await self.weekly_evolve_cycle(
                    queries=list(kwargs.get('queries') or []),
                    baseline_score=float(kwargs.get('baseline_score', 0.0) or 0.0),
                )
                return TaskResult(success=True, output=output)
            return TaskResult(success=False, error=f'unsupported task_type={task_type}')
        except Exception as exc:
            return TaskResult(success=False, error=str(exc))

    async def propose_and_benchmark(self, candidates: list[dict[str, Any]], baseline_score: float) -> dict[str, Any]:
        candidates = await self._expand_candidates_with_llm(candidates, baseline_score=baseline_score)
        result = self.benchmarks.evaluate(candidates, baseline_score=baseline_score)
        used_skills = [str(item.get("name") or "").strip() for item in self.skill_lib.retrieve("self healing benchmarks runtime", n=4)]
        owner_profile = self.owner_model.get_preferences() if hasattr(self.owner_model, "get_preferences") else {}
        issue_analysis = self._build_issue_analysis()
        for skill_name in used_skills[:4]:
            try:
                self.skill_lib.record_use(skill_name, success=bool(result.get("approved")))
            except Exception:
                pass
        if self.reflector and hasattr(self.reflector, 'reflect'):
            try:
                maybe = self.reflector.reflect(
                    category='technical',
                    action_type='self_evolver_v2',
                    input_summary=f"baseline={baseline_score}; candidates={len(candidates or [])}",
                    outcome_summary=str(result)[:1000],
                    success=bool(result.get("approved")),
                    context={"source": "self_evolver_v2", "factors": ["benchmarks", "discovery"]},
                )
                if hasattr(maybe, '__await__'):
                    await maybe
            except Exception:
                pass
        self.archive.record(
            archive_type="self_evolve_v2",
            title="benchmark_proposals",
            payload={"baseline_score": baseline_score, "candidates": candidates, "result": result},
            success=bool(result.get("approved")),
        )
        self.event_store.record_event(
            event_type="self_evolve_v2",
            source="self_evolver_v2",
            title="benchmark_proposals",
            status="ok" if result.get("approved") else "review",
            severity="info",
            payload={"baseline_score": baseline_score, "candidate_count": len(candidates or []), "approved": bool(result.get("approved"))},
        )
        result = dict(result or {})
        result["used_skills"] = used_skills[:4]
        result["runtime_profile"] = build_self_evolve_runtime_profile(
            proposal_count=len(candidates or []),
            issue_buckets=issue_analysis.get("issue_buckets") or {},
            owner_alignment=bool(owner_profile),
        )
        result["issue_analysis"] = issue_analysis
        result["benchmark_summary"] = {
            "baseline_score": float(baseline_score or 0.0),
            "candidate_count": len(candidates or []),
            "approved": bool(result.get("approved")),
            "owner_alignment": bool(owner_profile),
        }
        result["archive_ref"] = "self_evolve_v2:benchmark_proposals"
        result["candidates"] = candidates
        return result

    async def weekly_evolve_cycle(self, queries: list[str] | None = None, baseline_score: float = 0.0) -> dict[str, Any]:
        search_terms = [str(q).strip() for q in (queries or []) if str(q).strip()]
        if not search_terms:
            search_terms = [
                "python autonomous agents memory benchmark runtime",
                "python browser automation resilience",
                "python self-healing sandbox patch apply",
            ]
        candidates: list[dict[str, Any]] = []
        for query in search_terms[:3]:
            discovered = self.discovery.discover(query, limit=3)
            for item in list(discovered.get("items") or []):
                candidates.append(item)
        result = await self.propose_and_benchmark(candidates, baseline_score=baseline_score)
        payload = {
            "queries": search_terms,
            "candidate_count": len(candidates),
            "result": result,
            "proposals": list((result or {}).get("candidates") or candidates)[:4] if isinstance(result, dict) else candidates[:4],
            "used_skills": list((result or {}).get("used_skills") or []),
            "runtime_profile": dict((result or {}).get("runtime_profile") or {}),
            "issue_analysis": dict((result or {}).get("issue_analysis") or {}),
            "benchmark_summary": dict((result or {}).get("benchmark_summary") or {}),
            "archive_ref": "self_evolve_cycle:weekly_evolve_cycle",
        }
        self.archive.record(
            archive_type="self_evolve_cycle",
            title="weekly_evolve_cycle",
            payload=payload,
            success=bool(result.get("approved")),
        )
        self.event_store.record_event(
            event_type="self_evolve_cycle",
            source="self_evolver_v2",
            title="weekly_evolve_cycle",
            status="ok" if result.get("approved") else "review",
            severity="info",
            payload={"query_count": len(search_terms), "candidate_count": len(candidates), "approved": bool(result.get("approved"))},
        )
        return payload

    def _build_issue_analysis(self) -> dict[str, Any]:
        recent: list[str] = []
        if self.reflector and hasattr(self.reflector, "get_recent"):
            try:
                recent = [str(x) for x in self.reflector.get_recent(n=12, category="technical")]
            except Exception:
                recent = []
        buckets: dict[str, int] = {"browser": 0, "platform": 0, "auth": 0, "memory": 0, "general": 0}
        for issue in recent:
            low = issue.lower()
            if any(tok in low for tok in ["browser", "selector", "captcha", "upload"]):
                buckets["browser"] += 1
            elif any(tok in low for tok in ["etsy", "gumroad", "kdp", "printful", "platform"]):
                buckets["platform"] += 1
            elif any(tok in low for tok in ["auth", "login", "otp", "token"]):
                buckets["auth"] += 1
            elif any(tok in low for tok in ["memory", "skill", "retriev"]):
                buckets["memory"] += 1
            else:
                buckets["general"] += 1
        buckets = {k: v for k, v in buckets.items() if v > 0}
        dominant = max(buckets.items(), key=lambda item: item[1])[0] if buckets else "general"
        return {
            "issue_count": len(recent),
            "issue_buckets": buckets,
            "dominant_issue_bucket": dominant,
        }

    async def _expand_candidates_with_llm(self, candidates: list[dict[str, Any]], baseline_score: float) -> list[dict[str, Any]]:
        if not self.llm_router:
            return list(candidates or [])
        owner_profile = self.owner_model.get_preferences() if hasattr(self.owner_model, "get_preferences") else {}
        issue_analysis = self._build_issue_analysis()
        prompt = (
            "Предложи до 3 безопасных self-evolution кандидатов для VITO. "
            "Верни JSON-массив объектов {name, score, evidence, scenario_scores}. "
            "Не предлагай ничего destructive. "
            f"baseline={baseline_score}\n"
            f"existing={json.dumps(list(candidates or []), ensure_ascii=False)}\n"
            f"owner_profile={json.dumps(owner_profile, ensure_ascii=False)}\n"
            f"issue_analysis={json.dumps(issue_analysis, ensure_ascii=False)}"
        )
        try:
            raw = await self._call_llm(task_type=TaskType.STRATEGY, prompt=prompt, estimated_tokens=900)
        except Exception:
            raw = None
        parsed = self._parse_llm_candidates(raw)
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in list(candidates or []) + parsed:
            name = str(row.get("name") or "").strip().lower()
            if not name or name in seen:
                continue
            seen.add(name)
            merged.append(dict(row))
        return merged

    def _parse_llm_candidates(self, raw: Any) -> list[dict[str, Any]]:
        try:
            cleaned = str(raw or "").strip()
            if not cleaned:
                return []
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
            if isinstance(data, dict):
                data = data.get("items") or data.get("candidates") or []
            out: list[dict[str, Any]] = []
            for row in list(data or [])[:3]:
                if not isinstance(row, dict):
                    continue
                out.append({
                    "name": str(row.get("name") or "candidate").strip(),
                    "score": float(row.get("score", 0.0) or 0.0),
                    "evidence": dict(row.get("evidence") or {}),
                    "scenario_scores": list(row.get("scenario_scores") or []),
                })
            return out
        except Exception:
            return []
