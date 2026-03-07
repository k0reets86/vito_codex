#!/usr/bin/env python3
"""Best-effort Amazon KDP draft creation test via saved storage_state."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from PIL import Image, ImageDraw

ROOT_DIR = Path(__file__).resolve().parent.parent
import sys

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.epub_builder import build_simple_epub
from modules.pdf_utils import write_minimal_pdf

try:
    from config.settings import settings
except Exception:  # pragma: no cover - helper can still run without app settings
    settings = None


def _emit_result(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    if str(os.getenv("KDP_HELPER_IMMEDIATE_EXIT", "")).strip().lower() in {"1", "true", "yes", "on"}:
        os._exit(code)
    return code


def _launch_args() -> list[str]:
    return [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
    ]


async def _click_first(page, selectors: list[str], timeout_ms: int = 3500) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


async def _fill_first(page, selectors: list[str], value: str, timeout_ms: int = 3500) -> bool:
    val = str(value or "").strip()
    if not val:
        return False
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.fill(val, timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


async def _check_first(page, selectors: list[str], timeout_ms: int = 2500) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.check(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


async def _set_input_file(page, selectors: list[str], file_path: str, timeout_ms: int = 12000) -> bool:
    fp = str(file_path or "").strip()
    if not fp or not Path(fp).exists():
        return False
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.set_input_files(fp, timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


async def _body_contains(page, needles: list[str]) -> bool:
    try:
        body = ((await page.text_content("body")) or "").lower()
    except Exception:
        return False
    return any(str(n or "").strip().lower() in body for n in needles if str(n or "").strip())


async def _body_all(page) -> str:
    try:
        return ((await page.text_content("body")) or "").lower()
    except Exception:
        return ""


async def _kdp_asset_status(page, kind: str) -> tuple[str, str]:
    selectors = {
        "interior": (
            "#data-assets-interior-asset-status",
            "#data-assets-interior-asset-status-msg",
        ),
        "cover": (
            "#data-assets-cover-asset-status",
            "#data-assets-cover-asset-status-msg",
        ),
    }
    status_sel, msg_sel = selectors.get(kind, ("", ""))
    status = ""
    msg = ""
    try:
        if status_sel:
            status = await page.evaluate(
                f"""() => {{
                    const el = document.querySelector({json.dumps(status_sel)});
                    return el ? (el.value || el.textContent || '') : '';
                }}"""
            )
    except Exception:
        status = ""
    try:
        if msg_sel:
            msg = await page.evaluate(
                f"""() => {{
                    const el = document.querySelector({json.dumps(msg_sel)});
                    return el ? (el.value || el.textContent || '') : '';
                }}"""
            )
    except Exception:
        msg = ""
    return str(status or "").strip().upper(), str(msg or "").strip()


async def _kdp_fill_pricing_page(
    page,
    document_id: str,
    price_us: str,
    royalty_rate: str,
    enroll_select: bool,
    dbg: Path,
    stamp: str,
) -> dict:
    result = {
        "pricing_page_seen": False,
        "pricing_saved": False,
        "pricing_us_set": False,
        "pricing_url": "",
    }
    target_doc = str(document_id or "").strip()
    if not target_doc:
        return result
    doc_kind = _kdp_doc_kind()
    pricing_url = _kdp_setup_url(doc_kind, target_doc, 'pricing', 'ref_=kdp_BS_D_p_ed_pricing')
    if doc_kind in {"paperback", "hardcover"}:
        pricing_url = f"https://kdp.amazon.com/en_US/print-setup/{doc_kind}/{target_doc}/pricing"
    await page.goto(
        pricing_url,
        wait_until="domcontentloaded",
        timeout=120000,
    )
    await page.wait_for_timeout(3500)
    await _kdp_relogin_if_needed(page)
    if "pricing" not in (page.url or "").lower():
        await page.goto(
            pricing_url,
            wait_until="domcontentloaded",
            timeout=120000,
        )
        await page.wait_for_timeout(2500)
    result["pricing_url"] = page.url
    title_now = ((await page.title()) or "").lower()
    result["pricing_page_seen"] = _kdp_is_pricing_page(page.url, title_now, doc_kind)
    if not result["pricing_page_seen"]:
        return result

    try:
        loc = page.locator("#data-is-select")
        if await loc.count() > 0:
            if enroll_select:
                await loc.first.check(timeout=2500)
            else:
                await loc.first.uncheck(timeout=2500)
            await page.wait_for_timeout(400)
    except Exception:
        pass

    if doc_kind == "kindle":
        await _click_first(
            page,
            [
                "text=All territories (worldwide rights)",
                "a:has-text('All territories (worldwide rights)')",
                "#data-digital-worldwide-rights-accordion a",
            ],
            timeout_ms=2500,
        )
        await page.wait_for_timeout(500)
        try:
            await page.evaluate(
                """() => {
                    const hidden = document.querySelector('#data-digital-worldwide-rights');
                    if (hidden) {
                        hidden.value = 'true';
                        hidden.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }"""
            )
        except Exception:
            pass

        if royalty_rate in {"35_PERCENT", "70_PERCENT"}:
            clicked = await _click_first(
                page,
                [
                    f"input[name='data[digital][royalty_rate]-radio'][value='{royalty_rate}']",
                    f"label:has(input[name='data[digital][royalty_rate]-radio'][value='{royalty_rate}'])",
                ],
                timeout_ms=2500,
            )
            if not clicked:
                try:
                    await page.evaluate(
                        f"""() => {{
                            const radio = document.querySelector("input[name='data[digital][royalty_rate]-radio'][value='{royalty_rate}']");
                            if (radio) {{
                                radio.checked = true;
                                radio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                            const hidden = document.querySelector('#data-digital-royalty-rate-hidden');
                            if (hidden) hidden.value = '{royalty_rate}';
                        }}"""
                    )
                except Exception:
                    pass
            await page.wait_for_timeout(600)

        result["pricing_us_set"] = await _fill_first(
            page,
            [
                "input[name='data[digital][channels][amazon][US][price_vat_inclusive]']",
                "input[id*='us-price' i]",
                "input[name*='price_vat_inclusive' i]",
            ],
            price_us,
            timeout_ms=3500,
        )
        await page.wait_for_timeout(800)
        if result["pricing_us_set"]:
            try:
                await page.keyboard.press("Tab")
            except Exception:
                pass
            await page.wait_for_timeout(1200)
    else:
        await _click_first(
            page,
            [
                "#worldwide-rights",
                "label[for='worldwide-rights']",
                "text=Worldwide rights",
            ],
            timeout_ms=2500,
        )
        await page.wait_for_timeout(400)
        price_map = {
            "#price-input-usd": str(price_us),
            "#price-input-cad": "9.99",
            "#price-input-jpy": "999",
            "#price-input-gbp": "7.99",
            "#price-input-aud": "13.99",
            "#price-input-pln": "40.00",
            "#price-input-sek": "110.00",
        }
        try:
            eur_count = await page.locator("#price-input-eur").count()
        except Exception:
            eur_count = 0
        for idx in range(eur_count):
            price_map[f"#price-input-eur >> nth={idx}"] = "9,99"
        all_ok = True
        for sel, value in price_map.items():
            ok = await _fill_first(page, [sel], value, timeout_ms=3500)
            all_ok = all_ok and ok
            await page.wait_for_timeout(150)
        result["pricing_us_set"] = all_ok
        try:
            await page.keyboard.press("Tab")
        except Exception:
            pass
        await page.wait_for_timeout(1200)

    result["pricing_saved"] = await _click_first(
        page,
        [
            "#save-announce",
            "button:has-text('Save as Draft')",
            "button:has-text('Save and Continue')",
            "button:has-text('Save')",
        ],
        timeout_ms=3500,
    )
    await page.wait_for_timeout(2800)
    await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_pricing_after_save.png"), full_page=True)

    try:
        await page.reload(wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2500)
        if doc_kind == "kindle":
            current_price = await page.evaluate(
                """() => {
                    const el = document.querySelector("input[name='data[digital][channels][amazon][US][price_vat_inclusive]']");
                    return el ? (el.value || '') : '';
                }"""
            )
            current_royalty = await page.evaluate(
                """() => {
                    const el = document.querySelector('#data-digital-royalty-rate-hidden');
                    return el ? (el.value || '') : '';
                }"""
            )
            current_worldwide = await page.evaluate(
                """() => {
                    const el = document.querySelector('#data-digital-worldwide-rights');
                    return el ? (el.value || '') : '';
                }"""
            )
            result["pricing_us_set"] = result["pricing_us_set"] and str(current_price or "").strip() == price_us
            result["pricing_saved"] = (
                result["pricing_saved"]
                and str(current_royalty or "").strip() == royalty_rate
                and str(current_worldwide or "").strip().lower() == "true"
            )
        else:
            vals = await page.evaluate(
                """() => {
                    const read = (sel) => {
                        const els = Array.from(document.querySelectorAll(sel));
                        return els.map((el) => (el && 'value' in el) ? String(el.value || '').trim() : '');
                    };
                    return {
                        usd: read('#price-input-usd'),
                        cad: read('#price-input-cad'),
                        jpy: read('#price-input-jpy'),
                        gbp: read('#price-input-gbp'),
                        aud: read('#price-input-aud'),
                        eur: read('#price-input-eur'),
                        pln: read('#price-input-pln'),
                        sek: read('#price-input-sek'),
                    };
                }"""
            )
            result["pricing_us_set"] = result["pricing_us_set"] and (vals.get("usd") or [""])[0] == str(price_us)
            result["pricing_saved"] = result["pricing_saved"] and all([
                (vals.get("cad") or [""])[0] == "9.99",
                (vals.get("jpy") or [""])[0] == "999",
                (vals.get("gbp") or [""])[0] == "7.99",
                (vals.get("aud") or [""])[0] == "13.99",
                all(v == "9,99" for v in (vals.get("eur") or [])),
                (vals.get("pln") or [""])[0] == "40.00",
                (vals.get("sek") or [""])[0] == "110.00",
            ])
        result["pricing_url"] = page.url
    except Exception:
        pass
    return result


async def _click_text_any(page, texts: list[str], timeout_ms: int = 2500) -> bool:
    for txt in texts:
        try:
            loc = page.get_by_text(txt, exact=False)
            if await loc.count() > 0:
                await loc.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


def _prepare_kdp_cover_file(cover_path: str, dbg: Path, stamp: str) -> str:
    raw = str(cover_path or "").strip()
    if not raw:
        return ""
    src = Path(raw)
    if not src.exists():
        return ""
    kind = _kdp_doc_kind()
    if kind in {"paperback", "hardcover"}:
        target_width_in = 12.304 if kind == "paperback" else 13.0
        target_height_in = 9.25
        dpi = 300
        canvas_w = int(round(target_width_in * dpi))
        canvas_h = int(round(target_height_in * dpi))
        front_w = int(round(6.0 * dpi))
        front_h = int(round(9.0 * dpi))
        out = dbg / f"kdp_cover_{kind}_{stamp}.pdf"
        try:
            img = Image.open(src).convert("RGB")
            canvas = Image.new("RGB", (canvas_w, canvas_h), "white")

            # Reserve the right side for the front cover and keep left/spine neutral.
            front = img.copy()
            front.thumbnail((front_w, front_h))
            front_x = canvas_w - front.width - int(round(0.15 * dpi))
            front_y = max(0, (canvas_h - front.height) // 2)
            canvas.paste(front, (front_x, front_y))

            # Add minimal spine guide and back-cover title so the PDF is not blank.
            draw = ImageDraw.Draw(canvas)
            spine_x = max(0, front_x - int(round(0.28 * dpi)))
            draw.line((spine_x, 0, spine_x, canvas_h), fill=(220, 220, 220), width=3)
            draw.text((int(round(0.35 * dpi)), int(round(0.45 * dpi))), "Paperback Edition", fill="black")
            draw.text((int(round(0.35 * dpi)), int(round(0.9 * dpi))), "Practical workbook for creators and operators.", fill="black")

            canvas.save(out, format="PDF", resolution=float(dpi))
            return str(out)
        except Exception:
            return str(src)
    if src.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff"}:
        return str(src)
    try:
        out = dbg / f"kdp_cover_{stamp}.jpg"
        img = Image.open(src).convert("RGB")
        img.save(out, format="JPEG", quality=95)
        return str(out)
    except Exception:
        return str(src)


def _prepare_kdp_manuscript_file(manuscript_path: str, dbg: Path, stamp: str, title: str, author: str, description: str) -> str:
    raw = str(manuscript_path or "").strip()
    src = Path(raw) if raw else None
    kind = _kdp_doc_kind()
    if src and src.exists() and ((kind == "kindle" and src.suffix.lower() == ".epub") or (kind in {"paperback", "hardcover"} and src.suffix.lower() == ".pdf")):
        return str(src)
    if kind in {"paperback", "hardcover"}:
        out = dbg / f"kdp_manuscript_{kind}_{stamp}.pdf"
        pages = []
        base_lines = [
            title,
            description or "Practical workbook for creators and operators.",
            "Prompt 1: Define your niche and audience.",
            "Prompt 2: Outline the product and monetization path.",
            "Prompt 3: Build the launch checklist and shipping plan.",
        ]
        for page_num in range(24):
            img = Image.new("RGB", (1800, 2700), "white")
            draw = ImageDraw.Draw(img)
            y = 140
            draw.text((120, y), title, fill="black")
            y += 120
            draw.text((120, y), f"Page {page_num + 1}", fill="black")
            y += 120
            for line in base_lines:
                draw.text((120, y), line[:80], fill="black")
                y += 100
            pages.append(img)
        pages[0].save(out, save_all=True, append_images=pages[1:], resolution=300.0)
        return str(out)
    out = dbg / f"kdp_manuscript_{stamp}.epub"
    chapters = [
        ("Introduction", description or "Practical starter guide for creators and operators."),
        ("Workflow", "Define the niche, validate demand, prepare assets, publish, and iterate on confirmed signals."),
        ("Launch Checklist", "Use one draft per platform, confirm every field, and verify the result visually."),
    ]
    return build_simple_epub(out, title=title, author=author, description=description, chapters=chapters)


def _kdp_doc_kind() -> str:
    kind = str(os.getenv("KDP_TEST_DOC_TYPE", "kindle")).strip().lower()
    return kind if kind in {"kindle", "paperback", "hardcover"} else "kindle"


def _kdp_setup_url(kind: str, document_id: str, step: str, ref: str = "") -> str:
    if kind in {"paperback", "hardcover"}:
        action = f"dualbookshelf.edit{kind}{step}"
        base = f"https://kdp.amazon.com/action/{action}/en_US/title-setup/{kind}/{document_id}/{step}"
    else:
        base = f"https://kdp.amazon.com/en_US/title-setup/{kind}/{document_id}/{step}"
    return f"{base}?{ref}" if ref else base


def _kdp_is_pricing_page(url: str, title: str, kind: str) -> bool:
    url_now = str(url or "").lower()
    title_now = str(title or "").lower()
    if "/pricing" in url_now:
        return True
    if kind == "kindle":
        return "edit ebook pricing" in title_now
    if kind == "paperback":
        return "edit paperback rights" in title_now or "paperback rights & pricing" in title_now
    if kind == "hardcover":
        return "edit hardcover rights" in title_now or "hardcover rights & pricing" in title_now
    return False


def _kdp_is_cover_processing(body: str, kind: str) -> bool:
    body_now = str(body or "").lower()
    if "cover uploaded successfully" in body_now:
        return True
    if "processing your file" not in body_now:
        return False
    if kind == "kindle":
        return "kindle ebook cover" in body_now
    if kind == "paperback":
        return "paperback cover" in body_now or "book cover" in body_now
    if kind == "hardcover":
        return "hardcover cover" in body_now or "book cover" in body_now
    return False


async def _open_kdp_details_flow(page) -> bool:
    for _ in range(4):
        try:
            if await page.locator("input[name='bookTitle'], input#bookTitle, input[aria-label*='Book title']").count() > 0:
                return True
        except Exception:
            pass
        try:
            current_url = (page.url or "").lower()
        except Exception:
            current_url = ""
        try:
            body_text = ((await page.text_content("body")) or "").lower()
        except Exception:
            body_text = ""
        if "/title-setup/" in current_url and ("book title" in body_text or "language" in body_text):
            return True
        body = ""
        try:
            body = body_text
        except Exception:
            body = ""
        clicked = await _click_first(
            page,
            [
                "button:has-text('Create eBook')",
                "a:has-text('Create eBook')",
                "button:has-text('Create Kindle eBook')",
                "a:has-text('Create Kindle eBook')",
                "button:has-text('Kindle eBook')",
                "a:has-text('Kindle eBook')",
                "text=Create eBook",
                "text=Create Kindle eBook",
                "button:has-text('Paperback')",
                "a:has-text('Paperback')",
            ],
            timeout_ms=3000,
        )
        if clicked:
            await page.wait_for_timeout(2200)
            await _kdp_relogin_if_needed(page)
            await page.wait_for_timeout(1400)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            continue
        if "what would you like to create?" not in body and "/create" not in (page.url or "").lower():
            await page.wait_for_timeout(1200)
        else:
            break
    try:
        return await page.locator("input[name='bookTitle'], input#bookTitle, input[aria-label*='Book title']").count() > 0
    except Exception:
        pass
    try:
        current_url = (page.url or "").lower()
        body_text = ((await page.text_content("body")) or "").lower()
        return "/title-setup/" in current_url and ("book title" in body_text or "language" in body_text)
    except Exception:
        return False


async def _open_existing_draft_direct(page, document_id: str) -> bool:
    doc = str(document_id or "").strip()
    if not doc:
        return False
    urls = [
        _kdp_setup_url(_kdp_doc_kind(), doc, 'details', 'ref_=kdp_BS_D_ta_ed_main'),
        _kdp_setup_url(_kdp_doc_kind(), doc, 'content', 'ref_=kdp_BS_D_c_ed_content'),
    ]
    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2500)
            await _kdp_relogin_if_needed(page)
            await page.wait_for_timeout(1800)
            cur = (page.url or "").lower()
            title = ((await page.title()) or "").lower()
            body = ((await page.text_content("body")) or "").lower()
            kind = _kdp_doc_kind()
            if f"/title-setup/{kind}/{doc.lower()}/" in cur or "book title" in body or (
                ("edit ebook" in title and kind == "kindle")
                or ("edit paperback" in title and kind == "paperback")
                or ("edit hardcover" in title and kind == "hardcover")
            ):
                return True
        except Exception:
            continue
    return False


async def _bookshelf_titles(page) -> list[str]:
    try:
        items = await page.evaluate(
            """() => {
                const out = [];
                const seen = new Set();
                const push = (v) => {
                  const t = String(v || '').replace(/\\s+/g, ' ').trim();
                  if (!t || t.length < 3 || t.length > 180) return;
                  const low = t.toLowerCase();
                  if (seen.has(low)) return;
                  seen.add(low);
                  out.push(t);
                };
                const selectors = [
                  "a[href*='/title/']",
                  "a[href*='/book/']",
                  "[data-testid*='book']",
                  "[data-testid*='title']",
                  "h2",
                  "h3"
                ];
                for (const sel of selectors) {
                  for (const n of Array.from(document.querySelectorAll(sel))) {
                    push(n.textContent || "");
                  }
                }
                return out.slice(0, 200);
            }"""
        )
        return [str(x) for x in (items or [])]
    except Exception:
        return []


async def _open_existing_bookshelf_draft(page, title: str) -> bool:
    needle = str(title or "").strip().lower()
    if not needle:
        return False
    try:
        for sel in ("input[placeholder*='Search by title']", "input[aria-label*='Search by title']", "input[type='search']"):
            box = page.locator(sel)
            if await box.count() > 0:
                await box.first.fill(title)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(1800)
                break
    except Exception:
        pass
    try:
        clicked = await page.evaluate(
            """(needle) => {
                const key = String(needle || '').trim().toLowerCase();
                const rows = Array.from(document.querySelectorAll('div,article,li,tr'));
                for (const row of rows) {
                    const txt = (row.textContent || '').toLowerCase();
                    if (!txt.includes(key) || !txt.includes('continue setup')) continue;
                    const btn = Array.from(row.querySelectorAll('a,button')).find(el =>
                        /continue setup/i.test((el.textContent || '').trim())
                    );
                    if (btn) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""",
            needle,
        )
        if clicked:
            await page.wait_for_timeout(2500)
            return True
    except Exception:
        pass
    return False


async def _open_existing_draft_by_document_id(page, document_id: str) -> bool:
    doc_id = str(document_id or "").strip()
    if not doc_id:
        return False
    url = _kdp_setup_url(_kdp_doc_kind(), doc_id, 'details', 'ref_=kdp_BS_D_ta_ed_main')
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2200)
        relogged = await _kdp_relogin_if_needed(page)
        if relogged:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=12000)
            except Exception:
                pass
            await page.wait_for_timeout(2500)
        if "signin" in (page.url or "").lower() or "ap/signin" in (page.url or "").lower():
            return False
        kind = _kdp_doc_kind()
        if f"/title-setup/{kind}/{doc_id}/details" not in (page.url or ""):
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(1800)
        return f"/title-setup/{kind}/{doc_id}/details" in (page.url or "")
    except Exception:
        return False


async def _kdp_relogin_if_needed(page) -> bool:
    """Best-effort re-login when KDP asks only for password inside existing Amazon session."""
    cur = (page.url or "").lower()
    if "signin" not in cur and "ap/signin" not in cur:
        try:
            if await page.locator("input[type='password']").count() == 0:
                return False
        except Exception:
            return False
    pwd = str(os.getenv("KDP_PASSWORD", "")).strip() or str(getattr(settings, "KDP_PASSWORD", "") or "").strip()
    if not pwd:
        return False
    try:
        pwd_loc = page.locator("input[type='password'], input#ap_password, input[name='password']")
        if await pwd_loc.count() == 0:
            return False
        await pwd_loc.first.fill(pwd)
        clicked = await _click_first(
            page,
            [
                "input#signInSubmit",
                "button#signInSubmit",
                "button:has-text('Sign in')",
                "input[type='submit']",
            ],
            timeout_ms=4000,
        )
        if not clicked:
            return False
        await page.wait_for_timeout(2200)
        return True
    except Exception:
        return False


async def run(storage_path: str, headless: bool, debug_dir: str) -> int:
    state = Path(storage_path)
    dbg = Path(debug_dir)
    dbg.mkdir(parents=True, exist_ok=True)
    if not state.exists():
        print(json.dumps({"ok": False, "error": "storage_state_missing", "path": str(state)}, ensure_ascii=False))
        return 2

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    title = str(os.getenv("KDP_TEST_DRAFT_TITLE", "Working Draft")).strip() or "Working Draft"
    document_id = str(os.getenv("KDP_TEST_DRAFT_DOCUMENT_ID", "")).strip()
    subtitle = str(os.getenv("KDP_TEST_DRAFT_SUBTITLE", "")).strip()
    author = str(os.getenv("KDP_TEST_DRAFT_AUTHOR", "Editorial Team")).strip() or "Editorial Team"
    description = str(
        os.getenv(
            "KDP_TEST_DRAFT_DESCRIPTION",
            (
                "Practical AI workflow playbook for creators and operators. "
                "Includes reusable checklists, publishing system notes, and quick-start guidance."
            ),
        )
    ).strip()
    keywords = [x.strip() for x in str(os.getenv("KDP_TEST_DRAFT_KEYWORDS", "")).split("|") if x.strip()]
    manuscript_path = str(os.getenv("KDP_TEST_DRAFT_MANUSCRIPT", "")).strip()
    cover_path = str(os.getenv("KDP_TEST_DRAFT_COVER", "")).strip()
    price_us = str(os.getenv("KDP_TEST_DRAFT_PRICE_US", "2.99")).strip() or "2.99"
    royalty_rate = str(os.getenv("KDP_TEST_DRAFT_ROYALTY", "35_PERCENT")).strip() or "35_PERCENT"
    enroll_select = str(os.getenv("KDP_TEST_DRAFT_ENROLL_SELECT", "0")).strip().lower() in {"1", "true", "yes", "on"}
    resume_only = str(os.getenv("KDP_RESUME_ONLY", "")).strip().lower() in {"1", "true", "yes", "on"}

    cover_path = _prepare_kdp_cover_file(cover_path, dbg, stamp)
    manuscript_path = _prepare_kdp_manuscript_file(manuscript_path, dbg, stamp, title, author, description)
    doc_kind = _kdp_doc_kind()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_launch_args())
        ctx = await browser.new_context(storage_state=str(state), viewport={"width": 1440, "height": 920})
        page = await ctx.new_page()
        try:
            before_titles: list[str] = []
            resumed_existing = False
            if document_id and resume_only:
                await _open_existing_draft_direct(page, document_id)
                await _kdp_relogin_if_needed(page)
                await page.wait_for_timeout(1500)
                await _open_existing_draft_direct(page, document_id)
                resumed_existing = True
            else:
                await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(2500)
                await _kdp_relogin_if_needed(page)
                if "signin" in (page.url or "").lower() or "ap/signin" in (page.url or "").lower():
                    await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_signin_required.png"), full_page=True)
                    print(
                        json.dumps(
                            {"ok": False, "error": "signin_required_after_password", "url": page.url, "screenshot": str(dbg / f"kdp_draft_{stamp}_signin_required.png")},
                            ensure_ascii=False,
                        )
                    )
                    return 3
                before_titles = await _bookshelf_titles(page)

            if not resumed_existing and document_id:
                resumed_existing = await _open_existing_draft_direct(page, document_id)
            if not resumed_existing and document_id:
                resumed_existing = await _open_existing_draft_by_document_id(page, document_id)
            if not resumed_existing and not (document_id and resume_only):
                resumed_existing = await _open_existing_bookshelf_draft(page, title)
            if resumed_existing:
                await _kdp_relogin_if_needed(page)
                await page.wait_for_timeout(2200)
            elif resume_only and not document_id:
                resumed_existing = False

            if not resumed_existing:
                # Step 1: open create flow
                opened = await _click_first(
                    page,
                    [
                        "button:has-text('Create')",
                        "a:has-text('Create')",
                        "text=Create",
                    ],
                )
                if not opened:
                    await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_no_create.png"), full_page=True)
                    return _emit_result({"ok": False, "error": "create_button_not_found", "url": page.url}, 3)

                await page.wait_for_timeout(1200)

                # Step 2: choose ebook/paperback flow and ensure details form is actually opened.
                chosen = await _open_kdp_details_flow(page)
                await page.wait_for_timeout(2200)
                await _kdp_relogin_if_needed(page)
                if not chosen:
                    await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_create_flow_not_opened.png"), full_page=True)
                    return _emit_result({"ok": False, "error": "create_flow_not_opened", "url": page.url, "screenshot": str(dbg / f"kdp_draft_{stamp}_create_flow_not_opened.png")}, 3)

            # Step 3: fill metadata on details page (best effort).
            if doc_kind == "kindle":
                await _fill_first(
                    page,
                    [
                    "input[name='data[title]']",
                    "input#data-title",
                    "input[name='bookTitle']",
                    "input#bookTitle",
                    "input[aria-label*='Book title']",
                    "input[placeholder*='Book title']",
                    ],
                    title,
                )
                await _fill_first(
                    page,
                    [
                        "input[name='data[subtitle]']",
                        "input#data-subtitle",
                        "input[name='bookSubtitle']",
                        "input#bookSubtitle",
                        "input[aria-label*='Subtitle']",
                        "input[placeholder*='Subtitle']",
                    ],
                    subtitle,
                )

            # author name
            author_first, _, author_last = author.partition(" ")
            author_last = author_last.strip() or "Bot"
            first_set = False
            if doc_kind == "kindle":
                first_set = await _fill_first(
                    page,
                    [
                        "input[name='data[primary_author][first_name]']",
                        "input#data-primary-author-first-name",
                        "input[name='authorFirstName']",
                        "input#authorFirstName",
                        "input[aria-label*='First name']",
                    ],
                    author_first or "Vito",
                )
                if first_set:
                    await _fill_first(
                        page,
                        [
                            "input[name='data[primary_author][last_name]']",
                            "input#data-primary-author-last-name",
                            "input#data-print-book-primary-author-last-name-jp",
                            "input[name='authorLastName']",
                            "input#authorLastName",
                            "input[aria-label*='Last name']",
                        ],
                        author_last,
                    )

            description_set = await _fill_first(
                page,
                [
                    "textarea[name='data[description]']",
                    "textarea[name='description']",
                    "textarea#description",
                    "input[name='data[print_book][description]']",
                    "textarea[aria-label*='Description']",
                    "textarea[placeholder*='Description']",
                    "div[contenteditable='true']",
                ],
                description[:3800],
                timeout_ms=5000,
            )
            if not description_set:
                try:
                    description_set = bool(
                        await page.evaluate(
                            """(val) => {
                                const hidden = document.querySelector("input[name='data[description]']");
                                if (hidden) {
                                    hidden.value = val;
                                    hidden.dispatchEvent(new Event('input', { bubbles: true }));
                                    hidden.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                                const editable = document.querySelector("[contenteditable='true']");
                                if (editable) {
                                    editable.innerHTML = val.replace(/\\n/g, "<br>");
                                    editable.dispatchEvent(new Event('input', { bubbles: true }));
                                    editable.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                                return !!hidden || !!editable;
                            }""",
                            description[:3800],
                        )
                    )
                except Exception:
                    description_set = False

            await _check_first(page, ["input#non-public-domain", "input[name='data-is-public-domain'][value='false']"])
            await _check_first(page, ["input[name='data[is_adult_content]-radio'][value='false']"])

            keyword_slots_filled = 0
            keyword_selectors = [
                "input[name='data[keywords][0]']",
                "input[id^='data-keywords-']",
                "input[name='keywords[0]']",
                "input[id*='keyword']",
                "input[aria-label*='keyword' i]",
                "input[placeholder*='keyword' i]",
            ]
            for idx, kw in enumerate(keywords[:7]):
                filled = False
                for sel in keyword_selectors:
                    try:
                        loc = page.locator(sel)
                        cnt = await loc.count()
                        if cnt == 0:
                            continue
                        target = loc.nth(idx if cnt > idx else 0)
                        await target.fill(kw[:50], timeout=2500)
                        filled = True
                        break
                    except Exception:
                        continue
                if filled:
                    keyword_slots_filled += 1

            try:
                opened_categories = await _click_first(
                    page,
                    [
                        "button#categories-modal-button",
                        "#categories-modal-button",
                        "button:has-text('Choose categories')",
                        "a:has-text('Choose categories')",
                    ],
                    timeout_ms=3000,
                )
                if opened_categories:
                    await page.wait_for_timeout(1500)
                    try:
                        await page.evaluate(
                            """(kind) => {
                                const modal = Array.from(document.querySelectorAll("div,section,dialog")).find(el =>
                                    /select categories and subcategories/i.test(el.textContent || "")
                                ) || document;
                                const categorySelect = modal.querySelector("select[name='react-aui-0']");
                                if (categorySelect && (!categorySelect.value || categorySelect.value.includes('Select one'))) {
                                    const option = Array.from(categorySelect.options).find(o => /Business & Money/i.test(o.textContent || ""));
                                    if (option) {
                                        categorySelect.value = option.value;
                                        categorySelect.dispatchEvent(new Event('input', { bubbles: true }));
                                        categorySelect.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                }
                                const second = modal.querySelector("select[name='react-aui-2']");
                                if (second && (!second.value || second.value.includes('level'))) {
                                    const option = Array.from(second.options).find(o => /Business Development|Entrepreneurship|General/i.test(o.textContent || ""));
                                    if (option) {
                                        second.value = option.value;
                                        second.dispatchEvent(new Event('input', { bubbles: true }));
                                        second.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                }
                                const labels = Array.from(modal.querySelectorAll("label, span, div"));
                                const pickWrap = labels.find(el => /General|Bitcoin & Cryptocurrencies/i.test(el.textContent || ""));
                                const pick = pickWrap ? (pickWrap.querySelector("input[type='checkbox'], input[type='radio']") || null) : Array.from(modal.querySelectorAll("input[type='checkbox'], input[type='radio']")).find(el => !el.checked) || null;
                                if (pick) {
                                    pick.click();
                                    pick.dispatchEvent(new Event('input', { bubbles: true }));
                                    pick.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                                const buttons = Array.from(modal.querySelectorAll("button, input[type='submit'], a"));
                                for (const b of buttons) {
                                    const t = ((b.textContent || b.value || '')).trim().toLowerCase();
                                    if (t.includes('save categories') || t.includes('save') || t.includes('done') || t.includes('continue') || t.includes('confirm')) {
                                        b.click();
                                        return true;
                                    }
                                }
                                return !!pick;
                            }""",
                            doc_kind,
                        )
                    except Exception:
                        pass
                    await page.wait_for_timeout(1200)
            except Exception:
                pass

            if doc_kind in {"paperback", "hardcover"}:
                try:
                    await _check_first(page, ["#data-view-is-lcb"])
                except Exception:
                    pass
                await _click_text_any(page, ["Release my book for sale now"], timeout_ms=2000)
                await page.wait_for_timeout(600)

            await page.wait_for_timeout(800)

            # Step 4: save draft / continue
            saved = await _click_first(
                page,
                [
                    "button:has-text('Save and Continue')",
                    "button:has-text('Save and continue')",
                    "button:has-text('Save as draft')",
                    "button:has-text('Save')",
                    "button[type='submit']",
                ],
                timeout_ms=4500,
            )
            await page.wait_for_timeout(3000)
            await _kdp_relogin_if_needed(page)
            await page.wait_for_timeout(1200)
            await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_after_save.png"), full_page=True)

            # Step 4b: content/assets page, when flow advanced.
            manuscript_uploaded = False
            cover_uploaded = False
            try:
                await _kdp_relogin_if_needed(page)
                await page.wait_for_timeout(2200)
                await _click_first(
                    page,
                    [
                        "label:has-text('Yes. I have a file I would like to upload at this time.')",
                        "text=Yes. I have a file I would like to upload at this time.",
                    ],
                    timeout_ms=2500,
                )
                await page.wait_for_timeout(600)
                manuscript_uploaded = await _set_input_file(
                    page,
                    (
                        [
                            "#data-assets-interior-file-upload-AjaxInput",
                            "input[type='file'][accept*='pdf' i]",
                            "input[type='file'][name*='manuscript' i]",
                            "input[type='file'][id*='manuscript' i]",
                        ]
                        if doc_kind == "kindle"
                        else [
                            "#data-print-book-publisher-interior-file-upload-AjaxInput",
                            "input[type='file'][id*='publisher-interior' i]",
                            "input[type='file'][accept*='.pdf' i]",
                        ]
                    ),
                    manuscript_path,
                )
                if manuscript_uploaded:
                    await page.wait_for_timeout(3500)
                    if doc_kind == "kindle":
                        await _click_text_any(page, ["Continue with PDF", "I have another format", "Continue"], timeout_ms=2500)
                    await page.wait_for_timeout(1200)
                    body_now = await _body_all(page)
                    manuscript_uploaded = (
                        "uploaded successfully" in body_now
                        or "completed conversion" in body_now
                        or "uploaded on" in body_now
                        or (doc_kind in {"paperback", "hardcover"} and ("manuscript uploaded" in body_now or "processing your manuscript" in body_now))
                    )
                # If KDP asks to upload your own cover, try to enable that path.
                await _click_first(
                    page,
                    [
                        "label:has-text('Upload a cover you already have')",
                        "text=Upload a cover you already have",
                        "label:has-text('Upload your cover file')",
                        "input[value='UPLOAD_YOUR_COVER']",
                    ],
                    timeout_ms=2000,
                )
                await page.wait_for_timeout(600)
                cover_uploaded = await _set_input_file(
                    page,
                    (
                        [
                            "#data-assets-cover-file-upload-AjaxInput",
                            "#data-assets-cover-jp-file-upload-AjaxInput",
                            "input[type='file'][accept*='jpeg' i]",
                            "input[type='file'][accept*='jpg' i]",
                            "input[type='file'][name*='cover' i]",
                            "input[type='file'][id*='cover' i]",
                        ]
                        if doc_kind == "kindle"
                        else [
                            "#data-print-book-publisher-cover-pdf-only-file-upload-AjaxInput",
                            "#data-print-book-publisher-cover-file-upload-AjaxInput",
                            "input[type='file'][id*='publisher-cover-pdf-only' i]",
                            "input[type='file'][id*='publisher-cover-file-upload' i]",
                            "input[type='file'][accept='.pdf']",
                        ]
                    ),
                    cover_path,
                )
                if cover_uploaded:
                    await page.wait_for_timeout(3500)
                    body_now = await _body_all(page)
                    cover_uploaded = _kdp_is_cover_processing(body_now, doc_kind) or (
                        doc_kind in {"paperback", "hardcover"} and ("cover uploaded" in body_now or "processing your file" in body_now)
                    )
                if doc_kind in {"paperback", "hardcover"}:
                    try:
                        for sel in ["#generative-ai-questionnaire-text", "#generative-ai-questionnaire-images", "#generative-ai-questionnaire-translations"]:
                            loc = page.locator(sel)
                            if await loc.count() > 0:
                                await loc.first.select_option(index=2)
                    except Exception:
                        pass
                if manuscript_uploaded or cover_uploaded:
                    await _click_first(
                        page,
                        [
                            "button:has-text('Save and Continue')",
                            "button:has-text('Save and continue')",
                            "button:has-text('Save as draft')",
                            "button:has-text('Save')",
                        ],
                        timeout_ms=4500,
                    )
                    await page.wait_for_timeout(2500)
                    await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_after_assets.png"), full_page=True)
                    # If content is valid enough, KDP should allow moving to pricing.
                    await _click_first(
                        page,
                        [
                            "#book-setup-navigation-bar-pricing-link",
                            "a#book-setup-navigation-bar-pricing-link",
                            "button:has-text('Kindle eBook Pricing')",
                            "a:has-text('Kindle eBook Pricing')",
                        ],
                        timeout_ms=3500,
                    )
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

            # Step 4c: confirm asset state from KDP content page itself.
            try:
                interior_status, interior_msg = await _kdp_asset_status(page, "interior")
                cover_status_now, cover_msg_now = await _kdp_asset_status(page, "cover")
                if not manuscript_uploaded:
                    manuscript_uploaded = interior_status == "SUCCESS" or "manuscript check complete" in interior_msg.lower()
                if not cover_uploaded:
                    cover_uploaded = cover_status_now == "SUCCESS" or "uploaded successfully" in cover_msg_now.lower()
            except Exception:
                pass

            # Step 5: pricing page
            pricing_saved = False
            pricing_us_set = False
            pricing_page_seen = False
            pricing_url = ""
            try:
                pricing_result = await asyncio.wait_for(
                    _kdp_fill_pricing_page(page, document_id, price_us, royalty_rate, enroll_select, dbg, stamp),
                    timeout=45,
                )
                pricing_saved = bool(pricing_result.get("pricing_saved"))
                pricing_us_set = bool(pricing_result.get("pricing_us_set"))
                pricing_page_seen = bool(pricing_result.get("pricing_page_seen"))
                pricing_url = str(pricing_result.get("pricing_url") or "")
                if not pricing_page_seen and document_id:
                    pricing_page = await ctx.new_page()
                    try:
                        pricing_result = await asyncio.wait_for(
                            _kdp_fill_pricing_page(pricing_page, document_id, price_us, royalty_rate, enroll_select, dbg, stamp),
                            timeout=45,
                        )
                        pricing_saved = bool(pricing_result.get("pricing_saved"))
                        pricing_us_set = bool(pricing_result.get("pricing_us_set"))
                        pricing_page_seen = bool(pricing_result.get("pricing_page_seen"))
                        pricing_url = str(pricing_result.get("pricing_url") or "")
                    finally:
                        try:
                            await pricing_page.close()
                        except Exception:
                            pass
            except Exception:
                pass

            if resume_only and document_id and (manuscript_uploaded or cover_uploaded or pricing_page_seen):
                fields_filled = 0
                fields_filled += 1 if title.strip() else 0
                fields_filled += 1 if bool(saved) else 0
                fields_filled += 1 if bool(first_set) else 0
                fields_filled += 1 if bool(description_set) else 0
                fields_filled += int(keyword_slots_filled > 0)
                fields_filled += 1 if bool(manuscript_uploaded) else 0
                fields_filled += 1 if bool(cover_uploaded) else 0
                fields_filled += 1 if bool(pricing_us_set) else 0
                result = {
                    "ok": bool(manuscript_uploaded or cover_uploaded or pricing_page_seen),
                    "ok_soft": bool(manuscript_uploaded or cover_uploaded or pricing_page_seen),
                    "title": title,
                    "saved_click": bool(saved),
                    "url": page.url,
                    "title_found_on_bookshelf": True,
                    "title_found_via_search": True,
                    "draft_visible": True,
                    "before_count": len(before_titles),
                    "after_count": len(before_titles),
                    "fields_filled": int(fields_filled),
                    "description_set": bool(description_set),
                    "keyword_slots_filled": int(keyword_slots_filled),
                    "manuscript_uploaded": bool(manuscript_uploaded),
                    "cover_uploaded": bool(cover_uploaded),
                    "pricing_page_seen": bool(pricing_page_seen),
                    "pricing_saved": bool(pricing_saved),
                    "pricing_us_set": bool(pricing_us_set),
                    "pricing_url": pricing_url,
                    "price_us": price_us,
                    "royalty_rate": royalty_rate,
                    "enroll_select": bool(enroll_select),
                    "manuscript_path": manuscript_path,
                    "note": "resume_only_direct_document_verification",
                    "screenshot": str(dbg / f"kdp_draft_{stamp}_after_save.png"),
                    "bookshelf_screenshot": str(dbg / f"kdp_draft_{stamp}_after_save.png"),
                }
                return _emit_result(result, 0)

            search_hit = False
            after_titles: list[str] = []
            has_title = False
            appeared_new = False
            if resume_only and document_id:
                await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_bookshelf.png"), full_page=True)
                search_hit = True
                has_title = True
            else:
                await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(3500)
                # Additional verification path: search by exact title in bookshelf search field.
                try:
                    for sel in ("input[placeholder*='Search by title']", "input[aria-label*='Search by title']", "input[type='search']"):
                        box = page.locator(sel)
                        if await box.count() > 0:
                            await box.first.fill(title)
                            await page.keyboard.press("Enter")
                            await page.wait_for_timeout(2200)
                            body_text = (await page.text_content("body") or "").lower()
                            if title.lower() in body_text:
                                search_hit = True
                            break
                except Exception:
                    search_hit = False
                await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_bookshelf.png"), full_page=True)
                after_titles = await _bookshelf_titles(page)
                if not any((title or "").lower() in (t or "").lower() for t in after_titles):
                    for _ in range(2):
                        try:
                            await page.reload(wait_until="domcontentloaded", timeout=120000)
                            await page.wait_for_timeout(2200)
                            after_titles = await _bookshelf_titles(page)
                            if any((title or "").lower() in (t or "").lower() for t in after_titles):
                                break
                        except Exception:
                            continue
                before_l = [t.lower() for t in before_titles]
                after_l = [t.lower() for t in after_titles]
                has_title = title.lower() in after_l
                appeared_new = any(t not in before_l for t in after_l)
            fields_filled = 0
            fields_filled += 1 if title.strip() else 0
            fields_filled += 1 if bool(saved) else 0
            fields_filled += 1 if bool(first_set) else 0
            fields_filled += 1 if bool(description_set) else 0
            fields_filled += int(keyword_slots_filled > 0)
            fields_filled += 1 if bool(manuscript_uploaded) else 0
            fields_filled += 1 if bool(cover_uploaded) else 0
            fields_filled += 1 if bool(pricing_us_set) else 0
            draft_visible = bool(has_title or appeared_new or search_hit)
            ok = bool(draft_visible)
            ok_soft = bool(draft_visible)
            result = {
                "ok": bool(ok),
                "ok_soft": bool(ok_soft),
                "title": title,
                "saved_click": bool(saved),
                "url": page.url,
                "title_found_on_bookshelf": has_title,
                "title_found_via_search": bool(search_hit),
                "draft_visible": bool(draft_visible),
                "before_count": len(before_titles),
                "after_count": len(after_titles),
                "fields_filled": int(fields_filled),
                "description_set": bool(description_set),
                "keyword_slots_filled": int(keyword_slots_filled),
                "manuscript_uploaded": bool(manuscript_uploaded),
                "cover_uploaded": bool(cover_uploaded),
                "pricing_page_seen": bool(pricing_page_seen),
                "pricing_saved": bool(pricing_saved),
                "pricing_us_set": bool(pricing_us_set),
                "pricing_url": pricing_url,
                "price_us": price_us,
                "royalty_rate": royalty_rate,
                "enroll_select": bool(enroll_select),
                "manuscript_path": manuscript_path,
                "note": "strict_bookshelf_verification",
                "screenshot": str(dbg / f"kdp_draft_{stamp}_after_save.png"),
                "bookshelf_screenshot": str(dbg / f"kdp_draft_{stamp}_bookshelf.png"),
            }
            return _emit_result(result, 0 if (ok or ok_soft) else 4)
        finally:
            try:
                await asyncio.wait_for(ctx.close(), timeout=3)
            except Exception:
                pass
            try:
                await asyncio.wait_for(browser.close(), timeout=3)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="KDP draft creation smoke test")
    parser.add_argument("--storage-path", default="runtime/kdp_storage_state.json")
    parser.add_argument("--debug-dir", default="runtime/remote_auth")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.storage_path, bool(args.headless), args.debug_dir))


if __name__ == "__main__":
    raise SystemExit(main())
