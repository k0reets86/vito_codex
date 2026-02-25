#!/usr/bin/env python3
"""Generate capability pack report from spec.json files."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    packs_root = root / "capability_packs"
    rows = []
    for spec in packs_root.glob("*/spec.json"):
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({
            "name": data.get("name") or spec.parent.name,
            "category": data.get("category", ""),
            "status": data.get("acceptance_status", "pending"),
            "version": data.get("version", ""),
            "risk": data.get("risk_score", 0),
        })

    rows.sort(key=lambda r: r["name"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = root / "reports" / f"CAPABILITY_PACK_REPORT_{today}.md"
    lines = [f"# Capability Pack Report ({today})", "", "| Name | Category | Status | Version | Risk |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['category']} | {r['status']} | {r['version']} | {r['risk']} |")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
