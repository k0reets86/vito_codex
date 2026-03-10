
from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from modules.apply_engine import ApplyEngine
from modules.autonomy_runtime import build_self_evolve_runtime_profile
from modules.evolution_archive import EvolutionArchive
from modules.module_discovery import ModuleDiscovery
from modules.sandbox_manager import SandboxManager
from modules.skill_library import VITOSkillLibrary
from modules.vito_benchmarks import VITOBenchmarks


class SelfEvolverV2(BaseAgent):
    NEEDS = {
        'propose_and_benchmark': ['quality_judge', 'reflector', 'skill_library'],
        '*': ['reflector'],
    }

    def __init__(self, *, sandbox_manager: SandboxManager, apply_engine: ApplyEngine, benchmarks: VITOBenchmarks, discovery: ModuleDiscovery, reflector=None, archive: EvolutionArchive | None = None, **kwargs):
        super().__init__(name='self_evolver_v2', description='Benchmark-driven self-evolution engine', **kwargs)
        self.sandbox_manager = sandbox_manager
        self.apply_engine = apply_engine
        self.benchmarks = benchmarks
        self.discovery = discovery
        self.reflector = reflector
        self.archive = archive or EvolutionArchive()
        self.skill_lib = VITOSkillLibrary()

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
        result = self.benchmarks.evaluate(candidates, baseline_score=baseline_score)
        used_skills = [str(item.get("name") or "").strip() for item in self.skill_lib.retrieve("self healing benchmarks runtime", n=4)]
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
        result = dict(result or {})
        result["used_skills"] = used_skills[:4]
        result["runtime_profile"] = build_self_evolve_runtime_profile(
            proposal_count=len(candidates or []),
            issue_buckets={},
            owner_alignment=False,
        )
        result["archive_ref"] = "self_evolve_v2:benchmark_proposals"
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
            "archive_ref": "self_evolve_cycle:weekly_evolve_cycle",
        }
        self.archive.record(
            archive_type="self_evolve_cycle",
            title="weekly_evolve_cycle",
            payload=payload,
            success=bool(result.get("approved")),
        )
        return payload
