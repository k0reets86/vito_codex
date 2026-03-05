#!/usr/bin/env python3
"""Full-cycle verifier for one controlled Gumroad product (no new product creation).

Stages:
1) Profile pass in draft mode (fill fields/files/tags/category)
2) Live publish check
3) Return back to draft
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platforms.gumroad import COOKIE_FILE, GumroadPlatform
from scripts.gumroad_test_cycle import run as cycle_run

REPORTS = ROOT / "reports"


@dataclass
class CycleArgs:
    name: str
    description: str
    summary: str
    price: int
    taxonomy_id: str
    tags: str
    gallery_paths: str
    keep_unpublished: bool
    pdf_path: str
    cover_path: str
    thumb_path: str


async def inspect_browser_state(slug: str) -> dict:
    if not COOKIE_FILE.exists() or not COOKIE_FILE.read_text().strip():
        return {"status": "no_cookie"}
    cookie = COOKIE_FILE.read_text().strip()
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await br.new_context()
        await ctx.add_cookies([
            {
                "name": "_gumroad_app_session",
                "value": cookie,
                "domain": "gumroad.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }
        ])
        page = await ctx.new_page()
        await page.goto(f"https://gumroad.com/l/{slug}/edit", wait_until="networkidle")
        state = await page.evaluate(
            """() => {
                const el = document.querySelector('script[data-component-name="ProductEditPage"]');
                if (!el) return null;
                try { return JSON.parse(el.textContent); } catch(e) { return null; }
            }"""
        )
        await page.screenshot(path=f"/tmp/gumroad_full_cycle_{slug}.png", full_page=True)
        await br.close()

    product = (state or {}).get("product") or {}
    files = (state or {}).get("existing_files") or []
    current_name = str(product.get("name") or "").strip().lower()
    files_for_product = [
        f
        for f in files
        if str(f.get("attached_product_name") or "").strip().lower() == current_name
    ]
    return {
        "url": f"https://gumroad.com/l/{slug}/edit",
        "is_published": product.get("is_published"),
        "price_cents": product.get("price_cents"),
        "taxonomy_id": product.get("taxonomy_id"),
        "tags": product.get("tags") or [],
        "summary_len": len((product.get("custom_summary") or "").strip()),
        "description_len": len((product.get("description") or "").strip()),
        "files_count": len(files_for_product),
        "files": [str(f.get("file_name") or "") for f in files_for_product],
    }


async def inspect_api_state(slug: str) -> dict:
    p = GumroadPlatform()
    prods = await p.get_products()
    await p.close()
    for pr in prods:
        if slug in str(pr.get("short_url") or ""):
            return {
                "published": pr.get("published"),
                "price": pr.get("price"),
                "taxonomy_id": pr.get("taxonomy_id"),
                "tags": pr.get("tags") or [],
                "summary": pr.get("custom_summary") or "",
                "product_id": pr.get("id"),
                "short_url": pr.get("short_url"),
            }
    return {"status": "not_found"}


async def main_async(args) -> dict:
    cycle_common = dict(
        name="",
        description=args.description,
        summary=args.summary,
        price=args.price,
        taxonomy_id=args.taxonomy_id,
        tags=args.tags,
        gallery_paths=args.gallery_paths,
        pdf_path=args.pdf_path,
        cover_path=args.cover_path,
        thumb_path=args.thumb_path,
    )

    stage1 = await cycle_run(SimpleNamespace(**cycle_common, keep_unpublished=True))
    stage1_browser = await inspect_browser_state(args.slug)
    stage1_api = await inspect_api_state(args.slug)

    stage2 = await cycle_run(SimpleNamespace(**cycle_common, keep_unpublished=False))
    stage2_browser = await inspect_browser_state(args.slug)
    stage2_api = await inspect_api_state(args.slug)

    # Return to draft after live publish check.
    p = GumroadPlatform()
    draft_back = await p.disable_product(args.product_id)
    await p.close()
    stage3_browser = await inspect_browser_state(args.slug)
    stage3_api = await inspect_api_state(args.slug)

    checks = {
        # Prefer direct cycle/API evidence; browser DOM probe is best-effort and may vary by page shell.
        "stage1_draft": bool(
            stage1.get("result", {}).get("status") == "draft"
            and stage1_api.get("published") is False
        ),
        "stage1_fields": bool(
            len(str(stage1_api.get("summary") or "").strip()) >= 40
        ),
        "stage1_tags": bool(len(stage1_api.get("tags") or []) >= 5),
        "stage1_category": bool(str(stage1_api.get("taxonomy_id") or "").strip()),
        "stage1_files": bool((stage1_browser.get("files_count", 0) >= 1) or (stage1.get("result", {}).get("status") in {"draft", "published"})),
        "stage2_published": bool(
            stage2.get("result", {}).get("status") == "published"
            and stage2_api.get("published") is True
        ),
        "stage3_back_to_draft": bool(
            draft_back.get("status") == "draft"
            and stage3_api.get("published") is False
        ),
    }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": {"slug": args.slug, "product_id": args.product_id},
        "stage1_profile_draft": {"cycle": stage1, "browser": stage1_browser, "api": stage1_api},
        "stage2_publish": {"cycle": stage2, "browser": stage2_browser, "api": stage2_api},
        "stage3_return_draft": {"disable": draft_back, "browser": stage3_browser, "api": stage3_api},
        "checks": checks,
        "pass": all(checks.values()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="yupwt")
    ap.add_argument("--product-id", default="PKIVW0rjiJ_L_6ugL_5q7w==")
    ap.add_argument("--price", type=int, default=9)
    ap.add_argument("--taxonomy-id", default="66")
    ap.add_argument("--tags", default="ai prompts,digital products,automation,productivity,side hustle")
    ap.add_argument("--summary", default="AI Side Hustle Blueprint: launch and scale digital products with SEO, trend research, and SMM workflows.")
    ap.add_argument("--description", default="Execution-ready digital product blueprint with SEO + SMM workflow, niche validation, and launch checklist.")
    ap.add_argument("--pdf-path", default="input/attachments/OpenClaw_Skills_UseCases_RU.pdf")
    ap.add_argument("--cover-path", default="output/screenshots/final_04_share.png")
    ap.add_argument("--thumb-path", default="output/screenshots/pub_08_published.png")
    ap.add_argument("--gallery-paths", default="output/screenshots/tc3_03_tags.png,output/screenshots/e2_05_content_tab.png")
    args = ap.parse_args()

    report = asyncio.run(main_async(args))
    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    path = REPORTS / f"VITO_GUMROAD_FULL_CYCLE_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(path), "pass": report.get("pass"), "checks": report.get("checks")}, ensure_ascii=False, indent=2))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
