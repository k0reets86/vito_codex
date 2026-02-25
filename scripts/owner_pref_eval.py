#!/usr/bin/env python3
"""Simple owner preference eval (uses stored prefs only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.owner_preference_model import OwnerPreferenceModel


def main() -> int:
    model = OwnerPreferenceModel()
    prefs = model.list_preferences(limit=200)
    print(f"prefs_count={len(prefs)}")
    for p in prefs[:20]:
        print(f"- {p.get('pref_key')}: {p.get('value')} (conf={float(p.get('confidence',0)):.2f}, status={p.get('status')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
