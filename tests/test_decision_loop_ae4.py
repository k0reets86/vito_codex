import asyncio

from decision_loop import DecisionLoop
from goal_engine import GoalEngine
from llm_router import LLMRouter
from memory.memory_manager import MemoryManager
from modules.autonomy_overseer import AutonomyOverseer
from modules.evolution_events import EvolutionEventStore
from modules.module_discovery import ModuleDiscovery


class _DummyDiscovery(ModuleDiscovery):
    def __init__(self):
        pass
    def discover(self, query: str, limit: int = 5):
        return {'query': query, 'items': [{'name': 'pkg', 'url': 'https://x', 'summary': 's', 'score': 0.9, 'tags': []}]}


def test_decision_loop_ae4_discovery_and_overseer(tmp_path, monkeypatch):
    db = tmp_path / 'vito.db'
    monkeypatch.setattr('config.settings.settings.SQLITE_PATH', str(db), raising=False)
    monkeypatch.setattr('config.settings.settings.EVOLUTION_DISCOVERY_ENABLED', True, raising=False)
    monkeypatch.setattr('config.settings.settings.EVOLUTION_DISCOVERY_INTERVAL_TICKS', 1, raising=False)
    monkeypatch.setattr('config.settings.settings.EVOLUTION_DISCOVERY_QUERIES', 'python agents', raising=False)
    monkeypatch.setattr('config.settings.settings.EVOLUTION_OVERSEER_ENABLED', True, raising=False)
    monkeypatch.setattr('config.settings.settings.EVOLUTION_OVERSEER_INTERVAL_TICKS', 1, raising=False)
    monkeypatch.setattr('config.settings.settings.VITO_EVOLUTION_ENABLED', True, raising=False)

    loop = DecisionLoop(GoalEngine(sqlite_path=str(db)), LLMRouter(), MemoryManager(), agent_registry=None)
    loop._module_discovery = _DummyDiscovery()
    loop._evolution_events = EvolutionEventStore(sqlite_path=str(db))
    loop._autonomy_overseer = AutonomyOverseer(stuck_tick_threshold=1)
    loop.memory = None
    loop._tick_count = 500
    loop.orchestrator.list_sessions = lambda limit=200: [{'goal_id': 'g1', 'state': 'running', 'last_tick': 1}]

    asyncio.run(loop._maybe_run_evolution_discovery())
    asyncio.run(loop._maybe_run_autonomy_overseer())

    events = loop._evolution_events.list_events(limit=20)
    kinds = {e['event_type'] for e in events}
    assert 'evolution_discovery' in kinds
    assert 'autonomy_overseer' in kinds
