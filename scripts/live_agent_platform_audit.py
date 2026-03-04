#!/usr/bin/env python3
"""Live audit for agent -> platform execution paths.

Runs platform actions through production agents (SMM/ECommerce/Publisher/Browser)
and stores a timestamped report in reports/.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROBE_FILE = ROOT / "AGENTS.md"

from agents.browser_agent import BrowserAgent
from agents.ecommerce_agent import ECommerceAgent
from agents.publisher_agent import PublisherAgent
from agents.quality_judge import QualityJudge
from agents.smm_agent import SMMAgent
from platforms.etsy import EtsyPlatform
from platforms.gumroad import GumroadPlatform
from platforms.kofi import KofiPlatform
from platforms.printful import PrintfulPlatform
from platforms.reddit import RedditPlatform
from platforms.twitter import TwitterPlatform
from platforms.wordpress import WordPressPlatform


class DummyLLMRouter:
    async def call_llm(self, *args, **kwargs):
        prompt = (kwargs.get("prompt") or "").lower()
        if "верни json" in prompt and "score" in prompt and "issues" in prompt:
            return '{"score": 8, "feedback": "Good enough for live audit", "issues": []}'
        return "Live platform audit probe text."

    def check_daily_limit(self) -> bool:
        return True

    def get_daily_spend(self) -> float:
        return 0.0


class DummyMemory:
    def __getattr__(self, _name):
        def _noop(*args, **kwargs):
            return None

        return _noop


class DummyFinance:
    def record_expense(self, *args, **kwargs):
        return None

    def check_expense(self, *args, **kwargs):
        return {"allowed": True, "action": "allow"}

    def get_daily_spend(self) -> float:
        return 0.0

    def get_daily_revenue(self) -> float:
        return 0.0


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _clip(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text[:limit]


async def _run_with_timeout(coro, timeout: int = 60) -> dict[str, Any]:
    try:
        res = await asyncio.wait_for(coro, timeout=timeout)
        row = {
            "success": bool(getattr(res, "success", False)),
            "error": getattr(res, "error", "") or "",
            "output": getattr(res, "output", None),
            "metadata": getattr(res, "metadata", None),
        }
        return row
    except Exception as e:
        return {"success": False, "error": str(e), "output": None}


async def run() -> dict[str, Any]:
    llm = DummyLLMRouter()
    memory = DummyMemory()
    finance = DummyFinance()
    deps = {"llm_router": llm, "memory": memory, "finance": finance, "comms": None}

    twitter = TwitterPlatform()
    reddit = RedditPlatform()
    etsy = EtsyPlatform()
    gumroad = GumroadPlatform()
    kofi = KofiPlatform()
    printful = PrintfulPlatform()
    wordpress = WordPressPlatform()

    browser = BrowserAgent(**deps)
    qj = QualityJudge(**deps)
    smm = SMMAgent(platforms={"twitter": twitter}, **deps)
    ecommerce = ECommerceAgent(
        platforms={
            "etsy": etsy,
            "gumroad": gumroad,
            "kofi": kofi,
            "printful": printful,
        },
        **deps,
    )
    publisher = PublisherAgent(quality_judge=qj, platforms={"wordpress": wordpress}, **deps)

    tag = _ts()
    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "live_agent_platform_audit",
        "checks": [],
    }

    try:
        report["checks"].append(
        {
            "agent": "browser_agent",
            "capability": "browse",
            "target": "https://example.com",
            "result": await _run_with_timeout(
                browser.execute_task("browse", url="https://example.com", selector="h1"), timeout=90
            ),
        }
        )

        report["checks"].append(
        {
            "agent": "smm_agent",
            "capability": "social_media",
            "target": "twitter",
            "result": await _run_with_timeout(
                smm.execute_task("social_media", platform="twitter", content=f"VITO live agent audit {tag}"),
                timeout=90,
            ),
        }
        )

        report["checks"].append(
        {
            "agent": "ecommerce_agent",
            "capability": "listing_create",
            "target": "gumroad",
            "result": await _run_with_timeout(
                ecommerce.execute_task(
                    "listing_create",
                    platform="gumroad",
                    data={
                        "name": f"VITO Agent Audit Product {tag}",
                        "description": "Live audit probe",
                        "price": 1,
                        "dry_run": False,
                        "pdf_path": str(PROBE_FILE),
                        "preview_path": str(PROBE_FILE),
                    },
                ),
                timeout=120,
            ),
        }
        )
        report["checks"].append(
        {
            "agent": "ecommerce_agent",
            "capability": "listing_create",
            "target": "printful",
            "result": await _run_with_timeout(
                ecommerce.execute_task(
                    "listing_create",
                    platform="printful",
                    data={
                        "sync_product": {"name": f"VITO Agent Audit {tag}"},
                        "sync_variants": [],
                        "dry_run": False,
                        "preview_path": str(PROBE_FILE),
                    },
                ),
                timeout=120,
            ),
        }
        )
        report["checks"].append(
        {
            "agent": "ecommerce_agent",
            "capability": "listing_create",
            "target": "etsy",
            "result": await _run_with_timeout(
                ecommerce.execute_task(
                    "listing_create",
                    platform="etsy",
                    data={
                        "title": f"VITO Agent Audit Listing {tag}",
                        "description": "Live audit probe",
                        "price": 5,
                        "quantity": 1,
                        "tags": ["vito", "audit"],
                        "taxonomy_id": 1,
                        "dry_run": False,
                        "preview_path": str(PROBE_FILE),
                    },
                ),
                timeout=120,
            ),
        }
        )
        report["checks"].append(
        {
            "agent": "ecommerce_agent",
            "capability": "listing_create",
            "target": "kofi",
            "result": await _run_with_timeout(
                ecommerce.execute_task(
                    "listing_create",
                    platform="kofi",
                    data={
                        "title": f"VITO Agent Audit Product {tag}",
                        "description": "Live audit probe",
                        "price": 1,
                        "dry_run": False,
                        "preview_path": str(PROBE_FILE),
                    },
                ),
                timeout=120,
            ),
        }
        )

        report["checks"].append(
        {
            "agent": "publisher_agent",
            "capability": "publish",
            "target": "wordpress",
            "result": await _run_with_timeout(
                publisher.execute_task(
                    "publish",
                    platform="wordpress",
                    title=f"VITO Agent Audit Post {tag}",
                    content="Live platform audit post body.",
                    tags=["vito", "audit"],
                ),
                timeout=120,
            ),
        }
        )

        report["direct_platform_probes"] = []
        for name, pl in {
            "twitter": twitter,
            "reddit": reddit,
            "etsy": etsy,
            "gumroad": gumroad,
            "kofi": kofi,
            "printful": printful,
            "wordpress": wordpress,
        }.items():
            auth_ok = False
            auth_error = ""
            try:
                auth_ok = bool(await asyncio.wait_for(pl.authenticate(), timeout=25))
            except Exception as e:
                auth_error = str(e)
            report["direct_platform_probes"].append(
                {"platform": name, "auth_ok": auth_ok, "auth_error": _clip(auth_error)}
            )

        ready = 0
        for row in report["checks"]:
            rr = row["result"]
            if rr.get("success") is True:
                ready += 1
                continue
            out = rr.get("output")
            status = out.get("status") if isinstance(out, dict) else None
            if status in {
                "created",
                "published",
                "prepared",
                "draft",
                "needs_oauth",
                "needs_browser_login",
                "not_authenticated",
                "not_configured",
            }:
                ready += 1
        total = len(report["checks"])
        report["summary"] = {
            "total_agent_checks": total,
            "combat_path_responding": ready,
            "responding_percent": round((ready / total) * 100.0, 2) if total else 0.0,
        }

        for row in report["checks"]:
            row["result"]["error"] = _clip(row["result"].get("error", ""))
            row["result"]["output"] = json.loads(json.dumps(row["result"].get("output", None), ensure_ascii=False, default=str))
        return report
    finally:
        for pl in [twitter, reddit, etsy, gumroad, kofi, printful, wordpress]:
            try:
                await pl.close()
            except Exception:
                pass
        try:
            await browser.close()
        except Exception:
            pass


def main() -> int:
    report = asyncio.run(run())
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    path = reports / f"VITO_AGENT_PLATFORM_LIVE_AUDIT_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PROBE_FILE = ROOT / "AGENTS.md"
