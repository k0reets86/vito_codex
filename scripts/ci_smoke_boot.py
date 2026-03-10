#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # CI smoke boot should test import/init deterministically, not browser/display side effects.
    os.environ.setdefault("VITO_ALLOW_MULTI", "1")
    os.environ.setdefault("TELEGRAM_OWNER_CHAT_ID", "1")
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    os.environ.setdefault("VITO_BOOTSTRAP_XVFB", "0")

    try:
        from main import VITO

        print("VITO import smoke ok")
        _ = VITO()
        print("VITO init smoke ok")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
