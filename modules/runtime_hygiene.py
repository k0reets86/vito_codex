from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any

from config.paths import PROJECT_ROOT


RUNTIME_SIMULATOR_ROOT = PROJECT_ROOT / "runtime" / "simulator"
REPORTS_ROOT = PROJECT_ROOT / "reports"
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
PROJECT_TRASH_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".learnings",
    "MagicMock",
}
PERMANENT_RUNTIME_DB_NAMES = {
    "knowledge_graph.db",
    "platform_auth_interrupts.db",
}
REPORT_RETENTION_SUFFIXES = {".json", ".txt", ".md"}


def _tracked_report_files(root: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", str(root)],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return set()
    tracked: set[str] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rel = str(Path(line).relative_to(root.name))
        except Exception:
            try:
                rel = str(Path(line).relative_to(root))
            except Exception:
                rel = Path(line).name
        tracked.add(rel)
        tracked.add(Path(rel).name)
    return tracked


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


@dataclass(frozen=True)
class ReportCleanupResult:
    removed_files: list[str]
    kept_files: list[str]
    root: str


@dataclass(frozen=True)
class RuntimeDbCleanupResult:
    removed_files: list[str]
    kept_files: list[str]
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


def cleanup_reports_artifacts(*, keep_latest: int = 120, apply: bool = True) -> ReportCleanupResult:
    root = REPORTS_ROOT
    if not root.exists():
        return ReportCleanupResult([], [], str(root))
    tracked = _tracked_report_files(root)
    files = [
        p for p in root.iterdir()
        if p.is_file()
        and p.suffix in REPORT_RETENTION_SUFFIXES
        and p.name not in tracked
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    keep = files[: max(0, int(keep_latest))]
    purge = files[max(0, int(keep_latest)) :]
    removed: list[str] = []
    for path in purge:
        if apply:
            path.unlink(missing_ok=True)
        removed.append(path.name)
    return ReportCleanupResult(
        removed_files=removed,
        kept_files=[p.name for p in keep],
        root=str(root),
    )


def cleanup_runtime_db_artifacts(*, apply: bool = True) -> RuntimeDbCleanupResult:
    root = RUNTIME_ROOT
    if not root.exists():
        return RuntimeDbCleanupResult([], [], str(root))
    removed: list[str] = []
    kept: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".db", ".sqlite3"}:
            continue
        try:
            rel = str(path.relative_to(PROJECT_ROOT))
        except ValueError:
            rel = str(path.relative_to(root.parent))
        # simulator dbs are retained via directory-level cleanup; don't double-delete here
        if path.is_relative_to(RUNTIME_SIMULATOR_ROOT):
            kept.append(rel)
            continue
        if path.name in PERMANENT_RUNTIME_DB_NAMES:
            kept.append(rel)
            continue
        if apply:
            path.unlink(missing_ok=True)
        removed.append(rel)
    return RuntimeDbCleanupResult(
        removed_files=removed,
        kept_files=kept,
        root=str(root),
    )


def runtime_hygiene_summary() -> dict[str, Any]:
    root = RUNTIME_SIMULATOR_ROOT
    dirs = [p for p in root.iterdir() if p.is_dir()] if root.exists() else []
    report_files = [p for p in REPORTS_ROOT.iterdir() if p.is_file()] if REPORTS_ROOT.exists() else []
    runtime_dbs = [
        str(p.relative_to(PROJECT_ROOT))
        for p in RUNTIME_ROOT.rglob("*")
        if p.is_file() and p.suffix in {".db", ".sqlite3"}
    ] if RUNTIME_ROOT.exists() else []
    return {
        "simulator_root": str(root),
        "simulator_dir_count": len(dirs),
        "latest_dirs": [p.name for p in sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)[:10]],
        "report_file_count": len(report_files),
        "runtime_db_count": len(runtime_dbs),
    }


def cleanup_project_artifacts(*, apply: bool = True) -> ProjectCleanupResult:
    removed_dirs: list[str] = []
    removed_files: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.exists():
            continue
        name = path.name
        if path.is_dir() and (
            name in PROJECT_TRASH_DIR_NAMES
            or name.startswith("<MagicMock")
            or str(path.relative_to(PROJECT_ROOT)).startswith("MagicMock/")
        ):
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
