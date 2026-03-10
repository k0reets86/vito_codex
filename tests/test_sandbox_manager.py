import asyncio
from pathlib import Path

from modules.sandbox_manager import SandboxManager


def test_sandbox_manager_create_run_destroy(tmp_path: Path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'README.md').write_text('hello')
    asyncio.run(_git(repo, 'init'))
    asyncio.run(_git(repo, 'config', 'user.email', 'ci@example.com'))
    asyncio.run(_git(repo, 'config', 'user.name', 'CI'))
    asyncio.run(_git(repo, 'add', 'README.md'))
    asyncio.run(_git(repo, 'commit', '-m', 'init'))

    manager = SandboxManager(base_path=repo, sandbox_root=tmp_path / 'sandboxes')
    sandbox_id, sandbox_path = asyncio.run(manager.create())
    assert sandbox_id.startswith('exp_')
    assert sandbox_path.exists()

    async def patch(path: Path):
        (path / 'README.md').write_text('patched')

    result = asyncio.run(manager.run_in_sandbox(sandbox_path, patch))
    assert result.success is True
    assert (sandbox_path / 'README.md').read_text() == 'patched'

    asyncio.run(manager.destroy(sandbox_path))
    assert not sandbox_path.exists()


async def _git(repo: Path, *args: str):
    proc = await asyncio.create_subprocess_exec('git', '-C', str(repo), *args)
    await proc.communicate()
    assert proc.returncode == 0
