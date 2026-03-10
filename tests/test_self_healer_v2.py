import asyncio
from pathlib import Path

from agents.self_healer_v2 import SelfHealerV2
from modules.apply_engine import ApplyEngine
from modules.sandbox_manager import SandboxManager


class DummyReflector:
    async def reflect(self, **kwargs):
        return kwargs


class DummyLegacyHealer:
    async def handle_error(self, agent, error, context=None):
        return {"resolved": True, "method": "legacy", "description": f"{agent}:{type(error).__name__}"}


def test_self_healer_v2_success(tmp_path: Path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'x.txt').write_text('old')
    _init_repo(repo)
    healer = SelfHealerV2(
        llm_router=None,
        memory=None,
        finance=None,
        comms=None,
        sandbox_manager=SandboxManager(base_path=repo, sandbox_root=tmp_path / 'sandboxes'),
        apply_engine=ApplyEngine(project_root=repo, backup_root=tmp_path / 'backups'),
        reflector=DummyReflector(),
    )
    result = asyncio.run(healer.heal(RuntimeError('x'), {'health_check': lambda: True}, {'x.txt': 'new'}))
    assert result['success'] is True
    assert (repo / 'x.txt').read_text() == 'new'


def test_self_healer_v2_bridge_to_legacy(tmp_path: Path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'x.txt').write_text('old')
    _init_repo(repo)
    healer = SelfHealerV2(
        llm_router=None,
        memory=None,
        finance=None,
        comms=None,
        sandbox_manager=SandboxManager(base_path=repo, sandbox_root=tmp_path / 'sandboxes'),
        apply_engine=ApplyEngine(project_root=repo, backup_root=tmp_path / 'backups'),
        reflector=DummyReflector(),
        legacy_healer=DummyLegacyHealer(),
    )
    result = asyncio.run(healer.handle_error("decision_loop", RuntimeError("x"), {}))
    assert result["resolved"] is True
    assert result["method"] == "legacy"


def _init_repo(project: Path):
    import subprocess
    subprocess.run(['git', '-C', str(project), 'init'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(project), 'config', 'user.email', 'ci@example.com'], check=True)
    subprocess.run(['git', '-C', str(project), 'config', 'user.name', 'CI'], check=True)
    subprocess.run(['git', '-C', str(project), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(project), 'commit', '-m', 'init'], check=True, capture_output=True)
