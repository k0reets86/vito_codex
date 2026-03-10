
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT
from modules.prompt_guard import has_prompt_injection_signals


@dataclass
class ApplySnapshot:
    snapshot_id: str
    head_commit: str
    backup_path: Path
    created_at: float


@dataclass
class ApplyResult:
    success: bool
    snapshot_id: str = ""
    applied_files: list[str] = field(default_factory=list)
    health_ok: bool = False
    rollback_performed: bool = False
    details: str = ""


class ApplyEngine:
    """Safe apply/rollback engine with snapshot and health verification."""

    def __init__(self, project_root: str | Path | None = None, backup_root: str | Path | None = None):
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.backup_root = Path(backup_root or (self.project_root / 'runtime' / 'evolution_backups')).resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def create_snapshot(self) -> ApplySnapshot:
        head_commit = self._git_output(['rev-parse', 'HEAD']).strip()
        snapshot_id = hashlib.sha1(f"{head_commit}:{time.time()}".encode()).hexdigest()[:12]
        backup_path = self.backup_root / snapshot_id
        shutil.copytree(self.project_root, backup_path, ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache', '.venv*', 'node_modules', 'runtime/evolution_backups'))
        return ApplySnapshot(snapshot_id=snapshot_id, head_commit=head_commit, backup_path=backup_path, created_at=time.time())

    async def apply_files(self, files: dict[str, str], health_check: Any = None) -> ApplyResult:
        snapshot = self.create_snapshot()
        try:
            self._guard_file_payloads(files)
            applied = []
            for rel, content in files.items():
                rel_path = Path(rel)
                target = (self.project_root / rel_path).resolve()
                if self.project_root not in target.parents and target != self.project_root:
                    raise ValueError(f'unsafe target path: {rel}')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                applied.append(str(rel_path))
            health_ok, details = await self.health_check(health_check)
            if not health_ok:
                self.rollback(snapshot)
                return ApplyResult(success=False, snapshot_id=snapshot.snapshot_id, applied_files=applied, health_ok=False, rollback_performed=True, details=details)
            return ApplyResult(success=True, snapshot_id=snapshot.snapshot_id, applied_files=applied, health_ok=True, details=details)
        except Exception as exc:
            self.rollback(snapshot)
            return ApplyResult(success=False, snapshot_id=snapshot.snapshot_id, rollback_performed=True, details=str(exc))

    async def health_check(self, health_check: Any = None) -> tuple[bool, str]:
        if health_check is None:
            return True, 'default-health-ok'
        if callable(health_check):
            maybe = health_check()
            if asyncio.iscoroutine(maybe):
                maybe = await maybe
            if isinstance(maybe, tuple):
                return bool(maybe[0]), str(maybe[1])
            return bool(maybe), 'callable-health'
        if isinstance(health_check, str):
            import urllib.request
            try:
                with urllib.request.urlopen(health_check, timeout=10) as resp:
                    code = int(getattr(resp, 'status', 200) or 200)
                    body = resp.read().decode(errors='replace')[:200]
                    return code < 400, f'http:{code}:{body}'
            except Exception as exc:
                return False, f'http-error:{exc}'
        return False, 'unsupported-health-check'

    def rollback(self, snapshot: ApplySnapshot) -> None:
        if not snapshot.backup_path.exists():
            return
        for item in self.project_root.iterdir():
            if item.name in {'.git', 'runtime'}:
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                try:
                    item.unlink()
                except OSError:
                    pass
        for item in snapshot.backup_path.iterdir():
            target = self.project_root / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

    def _guard_file_payloads(self, files: dict[str, str]) -> None:
        for rel, content in files.items():
            if has_prompt_injection_signals(str(content or '')):
                raise ValueError(f'guardrails blocked file payload for {rel}: prompt_injection_signal')

    def _git_output(self, args: list[str]) -> str:
        import subprocess
        proc = subprocess.run(['git', '-C', str(self.project_root), *args], capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or 'git command failed')
        return proc.stdout
