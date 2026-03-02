"""Helpers for single-instance runtime guard."""

from __future__ import annotations

from pathlib import Path


def read_pidfile(path: str) -> int | None:
    try:
        raw = Path(path).read_text(encoding="utf-8").strip()
        pid = int(raw)
        return pid if pid > 0 else None
    except Exception:
        return None


def write_pidfile(path: str, pid: int) -> None:
    Path(path).write_text(str(int(pid)), encoding="utf-8")


def list_vito_main_pids(proc_root: str = "/proc") -> list[int]:
    out: list[int] = []
    root = Path(proc_root)
    if not root.exists():
        return out
    for child in root.iterdir():
        if not child.name.isdigit():
            continue
        try:
            pid = int(child.name)
            cmdline = (child / "cmdline").read_bytes().decode("utf-8", errors="replace")
        except Exception:
            continue
        if "main.py" in cmdline and "python" in cmdline:
            out.append(pid)
    return sorted(set(out))


def select_primary_pid(pids: list[int], pidfile_pid: int | None = None) -> int | None:
    items = sorted({int(x) for x in pids if int(x) > 0})
    if not items:
        return None
    if pidfile_pid and pidfile_pid in items:
        return pidfile_pid
    return items[0]
