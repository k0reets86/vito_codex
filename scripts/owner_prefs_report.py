#!/usr/bin/env python3
"""Generate owner preference report."""
from __future__ import annotations

from datetime import datetime, timezone

from modules.owner_preference_model import OwnerPreferenceModel
from modules.owner_pref_metrics import OwnerPreferenceMetrics


def main() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefs = OwnerPreferenceModel().list_preferences(limit=200)
    metrics = OwnerPreferenceMetrics().summary()
    lines = [f"# Owner Preferences Report ({today})", "", "## Metrics"]
    for k, v in metrics.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Preferences")
    if not prefs:
        lines.append("- None")
    else:
        for p in prefs:
            lines.append(f"- {p.get('pref_key')}: {p.get('value')} (conf={float(p.get('confidence',0)):.2f}, status={p.get('status')})")
    out = f"/home/vito/vito-agent/reports/OWNER_PREFS_{today}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
