#!/usr/bin/env python3
"""Scaffold a new capability pack.

Usage:
  python3 scripts/create_capability_pack.py <name> <category>
"""
import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 scripts/create_capability_pack.py <name> <category>")
        return 1
    name = sys.argv[1].strip().lower().replace(" ", "_")
    category = sys.argv[2].strip().lower().replace(" ", "_")
    if not name or not category:
        print("Name and category are required")
        return 1
    if any(c for c in name if not (c.isalnum() or c in "_")):
        print("Name must be alnum/underscore")
        return 1

    root = Path(__file__).resolve().parent.parent
    pack_dir = root / "capability_packs" / name
    pack_dir.mkdir(parents=True, exist_ok=True)

    spec_path = pack_dir / "spec.json"
    adapter_path = pack_dir / "adapter.py"
    tests_dir = pack_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_path = tests_dir / f"test_{name}.py"

    spec = {
        "name": name,
        "category": category,
        "description": "",
        "inputs": [],
        "outputs": [],
        "version": "0.1.0",
        "risk_score": 0.2,
        "tests_coverage": 0.0,
        "acceptance_status": "pending",
        "evidence": "",
    }

    if not spec_path.exists():
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    if not adapter_path.exists():
        adapter_path.write_text(
            """# Capability pack adapter stub\n\n"""
            """def run(input_data: dict) -> dict:\n"""
            """    \"\"\"Execute capability pack.\"\"\"\n"""
            """    return {\"status\": \"todo\", \"output\": {}}\n""",
            encoding="utf-8",
        )

    if not test_path.exists():
        test_path.write_text(
            f"""def test_{name}_stub():\n    assert True\n""",
            encoding="utf-8",
        )

    print(f"Created: {pack_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
