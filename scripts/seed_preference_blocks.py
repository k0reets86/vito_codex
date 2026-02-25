#!/usr/bin/env python3
"""Seed default owner preference blocks if missing."""
from __future__ import annotations

from modules.owner_preference_model import OwnerPreferenceModel


DEFAULTS = {
    "priorities.roi_focus": True,
    "style.language": "ru",
    "style.verbosity": "concise",
    "constraints.require_approval_publish": True,
    "constraints.max_daily_spend": 10,
}


def main() -> int:
    model = OwnerPreferenceModel()
    for k, v in DEFAULTS.items():
        if model.get_preference(k) is None:
            model.set_preference(k, v, source="system", confidence=0.6, notes="default_seed")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
