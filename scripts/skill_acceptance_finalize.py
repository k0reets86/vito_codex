#!/usr/bin/env python3
"""Finalize pending skills acceptance based on latest validation result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.skill_registry import SkillRegistry


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tests-passed", action="store_true", help="mark pending skills as accepted")
    p.add_argument("--evidence", default="", help="test report path or id")
    p.add_argument("--validator", default="skill_acceptance_finalize")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    reg = SkillRegistry()
    changed = reg.auto_accept_pending(
        tests_passed=bool(args.tests_passed),
        evidence=args.evidence,
        validator=args.validator,
        notes=args.notes or f"finalized at {datetime.now(timezone.utc).isoformat()}",
    )
    print(f"pending_skills_finalized={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
