#!/usr/bin/env python3
"""Simple owner preference eval (uses stored prefs only)."""
from __future__ import annotations

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
