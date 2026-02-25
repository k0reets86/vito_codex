#!/usr/bin/env python3
"""Record a manual capability pack event to DataLake."""
from __future__ import annotations

import argparse

from modules.data_lake import DataLake


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("name")
    p.add_argument("--status", default="success")
    p.add_argument("--note", default="")
    args = p.parse_args()
    DataLake().record(agent="capability_pack", task_type=f"cap_pack:{args.name}", status=args.status, output={"note": args.note}, source="manual")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
