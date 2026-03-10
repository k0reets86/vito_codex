import asyncio
from pathlib import Path

from modules.apply_engine import ApplyEngine


def test_apply_engine_apply_and_health(tmp_path: Path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'a.txt').write_text('old')
    _init_repo(project)
    engine = ApplyEngine(project_root=project, backup_root=tmp_path / 'backups')

    result = asyncio.run(engine.apply_files({'a.txt': 'new'}, health_check=lambda: True))
    assert result.success is True
    assert result.health_ok is True
    assert (project / 'a.txt').read_text() == 'new'


def test_apply_engine_rolls_back_on_health_fail(tmp_path: Path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'a.txt').write_text('old')
    _init_repo(project)
    engine = ApplyEngine(project_root=project, backup_root=tmp_path / 'backups')

    result = asyncio.run(engine.apply_files({'a.txt': 'new'}, health_check=lambda: (False, 'bad')))
    assert result.success is False
    assert result.rollback_performed is True
    assert (project / 'a.txt').read_text() == 'old'


def _init_repo(project: Path):
    import subprocess
    subprocess.run(['git', '-C', str(project), 'init'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(project), 'config', 'user.email', 'ci@example.com'], check=True)
    subprocess.run(['git', '-C', str(project), 'config', 'user.name', 'CI'], check=True)
    subprocess.run(['git', '-C', str(project), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(project), 'commit', '-m', 'init'], check=True, capture_output=True)
