#!/usr/bin/env python3
"""Accept capability packs after tests are validated."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from modules.skill_registry import SkillRegistry


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tests-passed", action="store_true", help="mark pending packs as accepted")
    p.add_argument("--evidence", default="", help="test report path or id")
    args = p.parse_args()

    reg = SkillRegistry()
    changed = reg.auto_accept_pending(
        tests_passed=bool(args.tests_passed),
        evidence=args.evidence,
        validator="accept_capability_packs",
        notes=f"capability pack accept {datetime.now(timezone.utc).isoformat()}",
    )
    print(f"accepted={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
