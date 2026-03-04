#!/usr/bin/env python3
"""Controlled Gumroad test cycle.

Policy:
- First successful run creates exactly one new test product.
- Next runs update only that captured product_id/slug.
- Never touches any other listing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platforms.gumroad import GumroadPlatform

STATE_PATH = ROOT / "runtime" / "gumroad_test_state.json"
REPORTS = ROOT / "reports"


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def run(args) -> dict:
    state = _load_state()
    state_before = dict(state)
    p = GumroadPlatform()
    name = args.name or f"VITO TEST {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
    payload = {
        "name": name,
        "description": args.description or "Controlled test product by VITO.",
        "summary": args.summary or "Controlled single-product test flow.",
        "price": args.price,
        "pdf_path": args.pdf_path,
        "cover_path": args.cover_path,
        "thumb_path": args.thumb_path,
    }

    if state.get("product_id") and state.get("slug"):
        payload.update(
            {
                "allow_existing_update": True,
                "owner_edit_confirmed": True,
                "target_product_id": str(state["product_id"]),
                "target_slug": str(state["slug"]),
            }
        )

    out = await p.publish(payload)
    await p.close()

    url = str(out.get("url") or "")
    pid = str(out.get("product_id") or "")
    slug = ""
    if "/l/" in url:
        slug = url.split("/l/")[-1].split("?")[0]
    if pid and slug:
        state.update(
            {
                "product_id": pid,
                "slug": slug,
                "name": name,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _save_state(state)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state_before": state_before,
        "payload": {k: v for k, v in payload.items() if k not in {"description", "summary"}},
        "result": out,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    path = REPORTS / f"VITO_GUMROAD_TEST_CYCLE_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--price", type=int, default=1)
    parser.add_argument("--pdf-path", required=True)
    parser.add_argument("--cover-path", required=True)
    parser.add_argument("--thumb-path", required=True)
    args = parser.parse_args()
    out = asyncio.run(run(args))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
