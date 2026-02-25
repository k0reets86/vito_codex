#!/usr/bin/env python3
"""Generate capability pack matrix by category."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    packs_root = root / "capability_packs"
    by_cat = defaultdict(list)
    for spec in packs_root.glob("*/spec.json"):
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except Exception:
            continue
        by_cat[data.get("category", "unknown")].append(data.get("name") or spec.parent.name)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = root / "reports" / f"CAPABILITY_PACK_MATRIX_{today}.md"
    lines = [f"# Capability Pack Matrix ({today})", ""]
    for cat in sorted(by_cat.keys()):
        lines.append(f"## {cat}")
        for name in sorted(by_cat[cat]):
            lines.append(f"- {name}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
