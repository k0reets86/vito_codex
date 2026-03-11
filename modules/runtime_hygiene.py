from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT


RUNTIME_SIMULATOR_ROOT = PROJECT_ROOT / "runtime" / "simulator"
PROJECT_TRASH_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".learnings",
}


@dataclass(frozen=True)
class ProjectCleanupResult:
    removed_dirs: list[str]
    removed_files: list[str]
    root: str


@dataclass(frozen=True)
class RuntimeCleanupResult:
    removed_dirs: list[str]
    kept_dirs: list[str]
    root: str


def cleanup_simulator_artifacts(*, keep_latest: int = 20, apply: bool = True) -> RuntimeCleanupResult:
    root = RUNTIME_SIMULATOR_ROOT
    if not root.exists():
        return RuntimeCleanupResult([], [], str(root))
    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    keep = dirs[: max(0, int(keep_latest))]
    purge = dirs[max(0, int(keep_latest)) :]
    removed: list[str] = []
    for path in purge:
        if apply:
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
        removed.append(path.name)
    return RuntimeCleanupResult(
        removed_dirs=removed,
        kept_dirs=[p.name for p in keep],
        root=str(root),
    )


def runtime_hygiene_summary() -> dict[str, Any]:
    root = RUNTIME_SIMULATOR_ROOT
    dirs = [p for p in root.iterdir() if p.is_dir()] if root.exists() else []
    return {
        "simulator_root": str(root),
        "simulator_dir_count": len(dirs),
        "latest_dirs": [p.name for p in sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)[:10]],
    }


def cleanup_project_artifacts(*, apply: bool = True) -> ProjectCleanupResult:
    removed_dirs: list[str] = []
    removed_files: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.exists():
            continue
        name = path.name
        if path.is_dir() and (name in PROJECT_TRASH_DIR_NAMES or name.startswith("<MagicMock")):
            if apply:
                for child in sorted(path.rglob("*"), reverse=True):
                    if child.is_file() or child.is_symlink():
                        child.unlink(missing_ok=True)
                    elif child.is_dir():
                        child.rmdir()
                path.rmdir()
            removed_dirs.append(str(path.relative_to(PROJECT_ROOT)))
            continue
        if path.is_file() and path.suffix in {".pyc", ".pyo", ".tmp", ".bak", ".orig"}:
            if apply:
                path.unlink(missing_ok=True)
            removed_files.append(str(path.relative_to(PROJECT_ROOT)))
    return ProjectCleanupResult(
        removed_dirs=removed_dirs,
        removed_files=removed_files,
        root=str(PROJECT_ROOT),
    )
