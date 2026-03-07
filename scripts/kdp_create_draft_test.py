#!/usr/bin/env python3
"""Best-effort Amazon KDP draft creation test via saved storage_state."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from PIL import Image

try:
    from config.settings import settings
except Exception:  # pragma: no cover - helper can still run without app settings
    settings = None


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
    if src.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff"}:
        return str(src)
    try:
        out = dbg / f"kdp_cover_{stamp}.jpg"
        img = Image.open(src).convert("RGB")
        img.save(out, format="JPEG", quality=95)
        return str(out)
    except Exception:
        return str(src)


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
    url = f"https://kdp.amazon.com/en_US/title-setup/kindle/{doc_id}/details?ref_=kdp_BS_D_ta_ed_main"
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
        if f"/title-setup/kindle/{doc_id}/details" not in (page.url or ""):
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(1800)
        return f"/title-setup/kindle/{doc_id}/details" in (page.url or "")
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
    title = str(os.getenv("KDP_TEST_DRAFT_TITLE", "VITO TEST DRAFT")).strip() or "VITO TEST DRAFT"
    document_id = str(os.getenv("KDP_TEST_DRAFT_DOCUMENT_ID", "")).strip()
    subtitle = str(os.getenv("KDP_TEST_DRAFT_SUBTITLE", "")).strip()
    author = str(os.getenv("KDP_TEST_DRAFT_AUTHOR", "Vito Bot")).strip() or "Vito Bot"
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
    resume_only = str(os.getenv("KDP_RESUME_ONLY", "")).strip().lower() in {"1", "true", "yes", "on"}

    cover_path = _prepare_kdp_cover_file(cover_path, dbg, stamp)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_launch_args())
        ctx = await browser.new_context(storage_state=str(state), viewport={"width": 1440, "height": 920})
        page = await ctx.new_page()
        try:
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

            resumed_existing = False
            if document_id:
                resumed_existing = await _open_existing_draft_by_document_id(page, document_id)
            if not resumed_existing:
                resumed_existing = await _open_existing_bookshelf_draft(page, title)
            if resumed_existing:
                await _kdp_relogin_if_needed(page)
                await page.wait_for_timeout(2200)
            elif resume_only:
                await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_resume_only_not_found.png"), full_page=True)
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "ok_soft": False,
                            "error": "resume_only_existing_draft_not_found",
                            "title": title,
                            "url": page.url,
                            "screenshot": str(dbg / f"kdp_draft_{stamp}_resume_only_not_found.png"),
                        },
                        ensure_ascii=False,
                    )
                )
                return 4

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
                    print(json.dumps({"ok": False, "error": "create_button_not_found", "url": page.url}, ensure_ascii=False))
                    return 3

                await page.wait_for_timeout(1200)

                # Step 2: choose ebook/paperback flow and ensure details form is actually opened.
                chosen = await _open_kdp_details_flow(page)
                await page.wait_for_timeout(2200)
                await _kdp_relogin_if_needed(page)
                if not chosen:
                    await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_create_flow_not_opened.png"), full_page=True)
                    print(
                        json.dumps(
                            {
                                "ok": False,
                                "error": "create_flow_not_opened",
                                "url": page.url,
                                "screenshot": str(dbg / f"kdp_draft_{stamp}_create_flow_not_opened.png"),
                            },
                            ensure_ascii=False,
                        )
                    )
                    return 3

            # Step 3: fill metadata on details page (best effort).
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
                            """() => {
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
                                const picks = Array.from(modal.querySelectorAll("input[type='checkbox'], input[type='radio']")).filter(el => !el.checked);
                                const pick = picks[0] || null;
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
                            }"""
                        )
                    except Exception:
                        pass
                    await page.wait_for_timeout(1200)
            except Exception:
                pass

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
                    [
                        "#data-assets-interior-file-upload-AjaxInput",
                        "input[type='file'][accept*='pdf' i]",
                        "input[type='file'][name*='manuscript' i]",
                        "input[type='file'][id*='manuscript' i]",
                    ],
                    manuscript_path,
                )
                if manuscript_uploaded:
                    await page.wait_for_timeout(3500)
                    await _click_text_any(page, ["Continue with PDF", "I have another format"], timeout_ms=2500)
                    await page.wait_for_timeout(1200)
                    body_now = await _body_all(page)
                    manuscript_uploaded = (
                        "uploaded successfully" in body_now
                        or "completed conversion" in body_now
                        or "uploaded on" in body_now
                    )
                # If KDP asks to upload your own cover, try to enable that path.
                await _click_first(
                    page,
                    [
                        "label:has-text('Upload a cover you already have')",
                        "text=Upload a cover you already have",
                        "label:has-text('Upload your cover file')",
                        "label:has-text('Upload your cover file')",
                        "input[value='UPLOAD_YOUR_COVER']",
                    ],
                    timeout_ms=2000,
                )
                await page.wait_for_timeout(600)
                cover_uploaded = await _set_input_file(
                    page,
                    [
                        "#data-assets-cover-file-upload-AjaxInput",
                        "#data-assets-cover-jp-file-upload-AjaxInput",
                        "input[type='file'][accept*='jpeg' i]",
                        "input[type='file'][accept*='jpg' i]",
                        "input[type='file'][name*='cover' i]",
                        "input[type='file'][id*='cover' i]",
                    ],
                    cover_path,
                )
                if cover_uploaded:
                    await page.wait_for_timeout(3500)
                    body_now = await _body_all(page)
                    cover_uploaded = (
                        "cover uploaded successfully" in body_now
                        or ("processing your file" in body_now and "kindle ebook cover" in body_now)
                    )
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
            except Exception:
                pass

            # Step 5: strict verification on Bookshelf with retries (KDP list can refresh with delay).
            await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3500)
            # Additional verification path: search by exact title in bookshelf search field.
            search_hit = False
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
                "note": "strict_bookshelf_verification",
                "screenshot": str(dbg / f"kdp_draft_{stamp}_after_save.png"),
                "bookshelf_screenshot": str(dbg / f"kdp_draft_{stamp}_bookshelf.png"),
            }
            print(json.dumps(result, ensure_ascii=False))
            return 0 if (ok or ok_soft) else 4
        finally:
            await ctx.close()
            await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="KDP draft creation smoke test")
    parser.add_argument("--storage-path", default="runtime/kdp_storage_state.json")
    parser.add_argument("--debug-dir", default="runtime/remote_auth")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.storage_path, bool(args.headless), args.debug_dir))


if __name__ == "__main__":
    raise SystemExit(main())
