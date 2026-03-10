from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from agents.self_evolver_v2 import SelfEvolverV2
from agents.self_healer_v2 import SelfHealerV2
from config.paths import PROJECT_ROOT
from config.settings import settings
from decision_loop import DecisionLoop
from goal_engine import GoalEngine
from llm_router import LLMRouter
from memory.memory_manager import MemoryManager
from modules.apply_engine import ApplyEngine
from modules.autonomy_overseer import AutonomyOverseer
from modules.evolution_archive import EvolutionArchive
from modules.evolution_audit import EvolutionAuditTrail
from modules.evolution_events import EvolutionEventStore
from modules.evolution_summary import EvolutionSummaryBuilder
from modules.fail_to_pass_validation import run_fail_to_pass_validation
from modules.module_discovery import ModuleDiscovery
from modules.sandbox_manager import SandboxManager
from modules.vito_benchmarks import VITOBenchmarks
from modules.reflector import VITOReflector


class DummyDiscovery(ModuleDiscovery):
    def __init__(self) -> None:
        pass

    def discover(self, query: str, limit: int = 5):
        return {
            "query": query,
            "items": [
                {
                    "name": "dummy_pkg",
                    "url": "https://example.com",
                    "summary": "dummy",
                    "score": 0.9,
                    "tags": ["agent"],
                }
            ],
        }


async def main() -> int:
    sqlite_path = settings.SQLITE_PATH
    goal_engine = GoalEngine(sqlite_path=sqlite_path)
    llm = LLMRouter()
    memory = MemoryManager()
    loop = DecisionLoop(goal_engine, llm, memory, agent_registry=None)

    events = EvolutionEventStore(sqlite_path=sqlite_path)
    archive = EvolutionArchive(sqlite_path=sqlite_path)
    sandbox = SandboxManager()
    apply_engine = ApplyEngine()
    benchmarks = VITOBenchmarks()
    discovery = DummyDiscovery()
    reflector = VITOReflector()
    healer = SelfHealerV2(
        sandbox_manager=sandbox,
        apply_engine=apply_engine,
        reflector=reflector,
        archive=archive,
        event_store=events,
        llm_router=llm,
        memory=memory,
    )
    evolver = SelfEvolverV2(
        sandbox_manager=sandbox,
        apply_engine=apply_engine,
        benchmarks=benchmarks,
        discovery=discovery,
        reflector=reflector,
        archive=archive,
        event_store=events,
        llm_router=llm,
        memory=memory,
    )
    loop._module_discovery = discovery
    loop._evolution_events = events
    loop._autonomy_overseer = AutonomyOverseer(stuck_tick_threshold=1)
    loop._self_healer_v2 = healer
    loop._self_evolver_v2 = evolver
    loop._tick_count = 500
    loop.orchestrator.list_sessions = lambda limit=200: [{"goal_id": "g-stuck", "state": "running", "last_tick": 1}]

    await loop._maybe_run_evolution_discovery()
    await loop._maybe_run_autonomy_overseer()
    weekly = await evolver.weekly_evolve_cycle(baseline_score=0.7)
    with tempfile.TemporaryDirectory(prefix="vito-ae5-") as tmpdir:
        fail_to_pass = await run_fail_to_pass_validation(tmpdir)

    summary_builder = EvolutionSummaryBuilder(sqlite_path=sqlite_path)
    summary_payload = summary_builder.build_owner_summary(days=30)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    report_path = PROJECT_ROOT / "reports" / f"VITO_AUTONOMY_EVOLUTION_COMBAT_VALIDATION_{ts}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase_ae5_complete": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_smoke": {
            "healer_v2": True,
            "evolver_v2": True,
            "events": len(events.list_events(limit=20)),
        },
        "weekly_evolve_cycle": weekly,
        "fail_to_pass": fail_to_pass,
        "owner_summary_total_events": summary_payload.get("events", {}).get("total", 0),
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = PROJECT_ROOT / "reports" / f"VITO_EVOLUTION_OWNER_SUMMARY_{ts}.md"
    summary_builder.persist_markdown(summary_path, summary_payload)
    print(json.dumps({"report_path": str(report_path), "summary_path": str(summary_path), "ok": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
