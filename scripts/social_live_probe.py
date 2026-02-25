#!/usr/bin/env python3
"""Run safe live probe on configured social platforms.

Policy:
- Twitter: publish one probe tweet and delete it immediately (if allowed).
- Other social platforms: auth probe only in this step.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import settings
from modules.execution_facts import ExecutionFacts
from platforms.twitter import TwitterPlatform
from platforms.threads import ThreadsPlatform
from platforms.reddit import RedditPlatform
from platforms.tiktok import TikTokPlatform


async def run_probe() -> dict:
    out: dict = {"timestamp": datetime.now(timezone.utc).isoformat(), "steps": []}
    facts = ExecutionFacts()

    # Auth probes
    probes = [
        ("threads", ThreadsPlatform()),
        ("reddit", RedditPlatform()),
        ("tiktok", TikTokPlatform()),
    ]
    for name, pl in probes:
        ok = False
        try:
            ok = bool(await asyncio.wait_for(pl.authenticate(), timeout=15))
        except Exception:
            ok = False
        finally:
            try:
                await pl.close()
            except Exception:
                pass
        out["steps"].append({"platform": name, "auth_ok": ok})
        facts.record(
            action="platform:auth_probe",
            status="success" if ok else "failed",
            detail=f"{name} auth_probe",
            evidence=f"auth:{name}",
            source="social_live_probe",
            evidence_dict={"platform": name, "auth_ok": ok},
        )

    # Twitter live probe (publish + immediate delete)
    twitter_allowed = os.getenv("SOCIAL_LIVE_ALLOW_TWITTER", "0").lower() in {"1", "true", "yes", "on"}
    twitter_configured = bool(
        settings.TWITTER_BEARER_TOKEN
        and settings.TWITTER_CONSUMER_KEY
        and settings.TWITTER_ACCESS_TOKEN
        and settings.TWITTER_ACCESS_SECRET
    )
    tw = TwitterPlatform()
    if twitter_allowed and twitter_configured:
        msg = f"VITO live probe {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} #vito_probe"
        try:
            pub = await asyncio.wait_for(tw.publish({"text": msg}), timeout=30)
        except Exception as e:
            pub = {"platform": "twitter", "status": "error", "error": str(e)}
        step = {"platform": "twitter", "publish": pub}
        tid = str(pub.get("tweet_id", "")) if isinstance(pub, dict) else ""
        if tid:
            try:
                dele = await asyncio.wait_for(tw.delete_tweet(tid), timeout=20)
            except Exception as e:
                dele = {"platform": "twitter", "status": "error", "error": str(e)}
            step["delete"] = dele
        out["steps"].append(step)
    else:
        out["steps"].append(
            {"platform": "twitter", "skipped": True, "reason": "not_configured_or_not_allowed"}
        )
    try:
        await tw.close()
    except Exception:
        pass

    return out


def main() -> int:
    data = asyncio.run(run_probe())
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    p = reports / f"VITO_SOCIAL_LIVE_PROBE_{ts}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
