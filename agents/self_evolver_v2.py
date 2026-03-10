
from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from modules.apply_engine import ApplyEngine
from modules.module_discovery import ModuleDiscovery
from modules.sandbox_manager import SandboxManager
from modules.vito_benchmarks import VITOBenchmarks


class SelfEvolverV2(BaseAgent):
    NEEDS = {
        'propose_and_benchmark': ['quality_judge', 'reflector', 'skill_library'],
        '*': ['reflector'],
    }

    def __init__(self, *, sandbox_manager: SandboxManager, apply_engine: ApplyEngine, benchmarks: VITOBenchmarks, discovery: ModuleDiscovery, reflector=None, **kwargs):
        super().__init__(name='self_evolver_v2', description='Benchmark-driven self-evolution engine', **kwargs)
        self.sandbox_manager = sandbox_manager
        self.apply_engine = apply_engine
        self.benchmarks = benchmarks
        self.discovery = discovery
        self.reflector = reflector

    @property
    def capabilities(self) -> list[str]:
        return ['propose_and_benchmark', 'discover_modules']

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
            return TaskResult(success=False, error=f'unsupported task_type={task_type}')
        except Exception as exc:
            return TaskResult(success=False, error=str(exc))

    async def propose_and_benchmark(self, candidates: list[dict[str, Any]], baseline_score: float) -> dict[str, Any]:
        result = self.benchmarks.evaluate(candidates, baseline_score=baseline_score)
        if self.reflector and hasattr(self.reflector, 'reflect'):
            try:
                maybe = self.reflector.reflect(category='technical', title='self_evolver_v2', content=str(result))
                if hasattr(maybe, '__await__'):
                    await maybe
            except Exception:
                pass
        return result
