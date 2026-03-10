
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from config.paths import PROJECT_ROOT


@dataclass
class SandboxResult:
    sandbox_id: str
    sandbox_path: Path
    success: bool
    test_output: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class SandboxManager:
    """Create isolated git-worktree sandboxes for safe experiments."""

    def __init__(self, base_path: str | Path | None = None, sandbox_root: str | Path | None = None):
        self.base_path = Path(base_path or PROJECT_ROOT).resolve()
        self.sandbox_root = Path(sandbox_root or tempfile.gettempdir()).resolve() / 'vito_sandboxes'
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self._allowed_env = self._parse_allowed_env()

    async def create(self) -> tuple[str, Path]:
        sandbox_id = f"exp_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.sandbox_root / sandbox_id
        proc = await asyncio.create_subprocess_exec(
            'git', '-C', str(self.base_path), 'worktree', 'add', '--detach', str(sandbox_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Worktree create failed: {err.decode(errors='replace').strip()}")
        return sandbox_id, sandbox_path

    async def run_in_sandbox(
        self,
        sandbox_path: Path,
        patch_func: Callable[[Path], Awaitable[None] | None],
        timeout: int = 300,
        test_command: list[str] | None = None,
    ) -> SandboxResult:
        sandbox_id = sandbox_path.name
        try:
            maybe = patch_func(sandbox_path)
            if asyncio.iscoroutine(maybe):
                await maybe
            if test_command:
                result = await asyncio.wait_for(self._run_tests(sandbox_path, test_command), timeout=timeout)
            else:
                result = {"success": True, "test_output": "", "metrics": {}}
            return SandboxResult(sandbox_id=sandbox_id, sandbox_path=sandbox_path, **result)
        except asyncio.TimeoutError:
            return SandboxResult(sandbox_id=sandbox_id, sandbox_path=sandbox_path, success=False, error='TIMEOUT')
        except Exception as exc:
            return SandboxResult(sandbox_id=sandbox_id, sandbox_path=sandbox_path, success=False, error=str(exc))

    async def destroy(self, sandbox_path: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            'git', '-C', str(self.base_path), 'worktree', 'remove', '--force', str(sandbox_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        shutil.rmtree(sandbox_path, ignore_errors=True)

    async def _run_tests(self, sandbox_path: Path, test_command: list[str]) -> dict[str, Any]:
        env = self._build_subprocess_env()
        proc = await asyncio.create_subprocess_exec(
            *test_command,
            cwd=str(sandbox_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        out, _ = await proc.communicate()
        output = out.decode(errors='replace')
        metrics = self._parse_metrics(output)
        return {
            'success': proc.returncode == 0,
            'test_output': output,
            'metrics': metrics,
        }

    def _parse_allowed_env(self) -> set[str]:
        from config.settings import settings
        raw = str(getattr(settings, "EVOLUTION_SANDBOX_ALLOWED_ENV", "") or "")
        allowed = {x.strip() for x in raw.split(",") if x.strip()}
        allowed.update({"PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "VIRTUAL_ENV", "TZ"})
        return allowed

    def _build_subprocess_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in self._allowed_env:
            if key in os.environ:
                env[key] = os.environ[key]
        if "PATH" not in env:
            env["PATH"] = os.environ.get("PATH", "")
        return env

    def _parse_metrics(self, output: str) -> dict[str, Any]:
        import re
        passed = re.search(r'(\d+)\s+passed', output)
        failed = re.search(r'(\d+)\s+failed', output)
        return {
            'tests_passed': int(passed.group(1)) if passed else 0,
            'tests_failed': int(failed.group(1)) if failed else 0,
        }
