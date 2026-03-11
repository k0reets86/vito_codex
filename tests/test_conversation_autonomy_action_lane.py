from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.conversation_autonomy_action_lane import handle_autonomy_action


class DummyGoalEngine:
    def __init__(self):
        self.calls = []

    def create_goal(self, **kwargs):
        self.calls.append(kwargs)


class DummyProposals:
    def __init__(self):
        self.calls = []

    def mark_status(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class DummyRegistry:
    async def dispatch(self, task_type, **kwargs):
        return SimpleNamespace(success=True, error='', output={'task_type': task_type})


class DummyUpdater:
    def backup_current_code(self):
        return '/tmp/backup.zip'


class DummyEngine:
    def __init__(self):
        self.goal_engine = DummyGoalEngine()
        self.autonomy_proposals = DummyProposals()
        self.agent_registry = DummyRegistry()
        self.self_updater = DummyUpdater()

    async def _maybe_quality_gate(self, *args, **kwargs):
        return 'ok'


@pytest.mark.asyncio
async def test_run_social_pack_returns_summary():
    engine = DummyEngine()
    out = await handle_autonomy_action(engine, 'run_social_pack', {'topic': 'AI kit', 'channels': ['twitter', 'pinterest']})
    assert 'AI kit' in out
    assert 'x, pinterest' in out


@pytest.mark.asyncio
async def test_run_autonomy_proposal_creates_goal_and_marks_status():
    engine = DummyEngine()
    out = await handle_autonomy_action(engine, 'run_autonomy_proposal', {
        'proposal_id': 7,
        'proposal_kind': 'growth',
        'proposal': {'title': 'Launch new pack', 'why': 'owner value', 'expected_revenue': 15},
    })
    assert 'Launch new pack' in out
    assert engine.goal_engine.calls
    assert engine.autonomy_proposals.calls


@pytest.mark.asyncio
async def test_run_improvement_cycle_runs_backup_and_quality_gate():
    engine = DummyEngine()
    out = await handle_autonomy_action(engine, 'run_improvement_cycle', {'request': 'Improve weak agents'})
    assert 'Backup:' in out
    assert 'HR audit: ok' in out
    assert 'Research scan: ok' in out
    assert 'Self-improve: ok' in out
    assert 'Quality gate: ok' in out
