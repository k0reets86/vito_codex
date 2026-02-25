#!/usr/bin/env python3
"""Run a capability pack by name."""
from __future__ import annotations

import json
import sys

from modules.capability_pack_runner import CapabilityPackRunner


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/run_capability_pack.py <name> [json_input]")
        return 1
    name = sys.argv[1]
    input_data = {}
    if len(sys.argv) >= 3:
        try:
            input_data = json.loads(sys.argv[2])
        except Exception:
            input_data = {}
    res = CapabilityPackRunner().run(name, input_data)
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
