#!/usr/bin/env python3
"""Validate capability pack specs for required fields."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = {"name", "category", "inputs", "outputs", "version", "risk_score", "tests_coverage", "acceptance_status"}


def main() -> int:
    root = Path(__file__).resolve().parent.parent / "capability_packs"
    ok = True
    for spec in root.glob("*/spec.json"):
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except Exception:
            print(f"Invalid JSON: {spec}")
            ok = False
            continue
        missing = sorted(REQUIRED - set(data.keys()))
        if missing:
            print(f"Missing {missing} in {spec}")
            ok = False
    if ok:
        print("All capability pack specs valid")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
