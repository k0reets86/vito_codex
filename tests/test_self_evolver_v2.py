import asyncio

from agents.self_evolver_v2 import SelfEvolverV2
from modules.apply_engine import ApplyEngine
from modules.module_discovery import ModuleDiscovery
from modules.sandbox_manager import SandboxManager
from modules.vito_benchmarks import VITOBenchmarks


class DummyReflector:
    async def reflect(self, **kwargs):
        return kwargs


def test_self_evolver_v2_benchmark(tmp_path):
    evolver = SelfEvolverV2(
        llm_router=None,
        memory=None,
        finance=None,
        comms=None,
        sandbox_manager=SandboxManager(base_path=tmp_path, sandbox_root=tmp_path / 'sandboxes'),
        apply_engine=ApplyEngine(project_root=tmp_path, backup_root=tmp_path / 'backups'),
        benchmarks=VITOBenchmarks(threshold_delta=0.05),
        discovery=ModuleDiscovery(),
        reflector=DummyReflector(),
    )
    result = asyncio.run(evolver.propose_and_benchmark([
        {'name': 'proposal', 'score': 0.8, 'evidence': {'delta': 0.2}},
    ], baseline_score=0.7))
    assert result['approved'] is True
    assert result['best_score']['name'] == 'proposal'


def test_self_evolver_v2_weekly_cycle(tmp_path):
    evolver = SelfEvolverV2(
        llm_router=None,
        memory=None,
        finance=None,
        comms=None,
        sandbox_manager=SandboxManager(base_path=tmp_path, sandbox_root=tmp_path / 'sandboxes'),
        apply_engine=ApplyEngine(project_root=tmp_path, backup_root=tmp_path / 'backups'),
        benchmarks=VITOBenchmarks(threshold_delta=0.05),
        discovery=ModuleDiscovery(),
        reflector=DummyReflector(),
    )
    result = asyncio.run(evolver.weekly_evolve_cycle(["python runtime agents"], baseline_score=0.0))
    assert result["candidate_count"] >= 0
    assert "result" in result
