from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from modules.apply_engine import ApplyEngine


async def run_fail_to_pass_validation(project_root: str | Path) -> dict[str, Any]:
    project_root = Path(project_root)
    git_dir = project_root / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=str(project_root), check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "vito@example.local"], cwd=str(project_root), check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "VITO"], cwd=str(project_root), check=True, capture_output=True, text=True)
        seed = project_root / ".seed"
        seed.write_text("seed", encoding="utf-8")
        subprocess.run(["git", "add", ".seed"], cwd=str(project_root), check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=str(project_root), check=True, capture_output=True, text=True)
    engine = ApplyEngine(project_root=project_root)
    baseline = await engine.apply_files({'tmp_fail_to_pass.txt': 'baseline'}, health_check=lambda: (False, 'forced_fail'))
    patched = await engine.apply_files({'tmp_fail_to_pass.txt': 'patched'}, health_check=lambda: (True, 'forced_pass'))
    return {
        'baseline_failed': not baseline.success and bool(baseline.rollback_performed),
        'patched_passed': bool(patched.success and patched.health_ok),
        'baseline_snapshot': baseline.snapshot_id,
        'patched_snapshot': patched.snapshot_id,
    }
