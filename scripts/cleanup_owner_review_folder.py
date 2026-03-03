#!/usr/bin/env python3
"""Archive and cleanup owner review drop folder."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


def cleanup(
    src: Path,
    archive_root: Path,
    keep_days: int,
    apply: bool,
) -> dict:
    now = datetime.now(timezone.utc)
    archive_dir = archive_root / now.strftime("%Y%m%d_%H%M%S")
    files = [p for p in sorted(src.iterdir()) if p.is_file() and p.name != "README.txt"]

    moved = 0
    if files:
        if apply:
            archive_dir.mkdir(parents=True, exist_ok=True)
        for p in files:
            if apply:
                shutil.move(str(p), str(archive_dir / p.name))
            moved += 1

    removed_archives = 0
    cutoff = now - timedelta(days=max(1, keep_days))
    if archive_root.exists():
        for d in archive_root.iterdir():
            if not d.is_dir():
                continue
            dt = datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc)
            if dt < cutoff:
                if apply:
                    shutil.rmtree(d, ignore_errors=True)
                removed_archives += 1

    return {
        "source": str(src),
        "archive_dir": str(archive_dir),
        "moved_files": moved,
        "removed_old_archives": removed_archives,
        "apply": apply,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup owner review folder")
    parser.add_argument("--source", default="input/to_review")
    parser.add_argument("--archive-root", default="input/to_review_archive")
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument("--apply", action="store_true", help="perform changes (default is dry-run)")
    args = parser.parse_args()

    src = Path(args.source)
    archive_root = Path(args.archive_root)
    if not src.exists() or not src.is_dir():
        print(f"ERROR: source folder not found: {src}")
        return 1

    result = cleanup(src=src, archive_root=archive_root, keep_days=args.keep_days, apply=bool(args.apply))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
