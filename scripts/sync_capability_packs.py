#!/usr/bin/env python3
"""Register capability packs into SkillRegistry.

Usage:
  python3 scripts/sync_capability_packs.py [root]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.skill_registry import SkillRegistry


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "capability_packs"
    reg = SkillRegistry()
    count = reg.register_from_capability_packs(root=root)
    print(f"Registered {count} capability packs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
