#!/usr/bin/env python3
"""Upload 'The AI Side Hustle Playbook' to Gumroad.

Steps:
1. Convert MD ebook to clean PDF
2. Upload to Gumroad via API (POST /v2/products)
3. Enable (publish) the product
4. Report result
"""

import os
import sys
import re

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EBOOK_MD = Path(__file__).resolve().parent.parent / "output/ebooks/ai_side_hustle_playbook.md"
EBOOK_PDF = Path(__file__).resolve().parent.parent / "output/ebooks/ai_side_hustle_playbook.pdf"
LISTING_MD = Path(__file__).resolve().parent.parent / "output/products/ai_side_hustle_playbook_listing.md"

GUMROAD_TOKEN = os.getenv("GUMROAD_API_KEY", "")
API_BASE = "https://api.gumroad.com/v2"


def _safe_latin1(text: str) -> str:
    """Replace non-latin1 chars with closest ASCII equivalent."""
    replacements = {
        "\u2014": "--", "\u2013": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2022": "-",
        "\u2192": "->", "\u2714": "[x]", "\u2717": "[ ]",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def md_to_pdf(md_path: Path, pdf_path: Path) -> bool:
    """Convert markdown to PDF using fpdf2."""
    from fpdf import FPDF

    text = md_path.read_text(encoding="utf-8")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)  # Wider content area
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    line_h = 5

    # Remove markdown bold/italic markers
    def clean_md(s):
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        return _safe_latin1(s.strip())

    seen_headings = set()
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        i += 1

        if not stripped:
            pdf.ln(line_h)
            continue

        if stripped == "---":
            pdf.ln(line_h)
            continue

        # H1
        if stripped.startswith("# ") and not stripped.startswith("## "):
            heading = clean_md(stripped.lstrip("# "))
            if heading in seen_headings:
                continue  # Skip duplicate chapter titles
            seen_headings.add(heading)
            pdf.ln(line_h * 2)
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(0, 8, heading)
            pdf.ln(line_h)
            pdf.set_font("Helvetica", size=10)
            continue

        # H2
        if stripped.startswith("## "):
            heading = clean_md(stripped.lstrip("# "))
            pdf.ln(line_h)
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 7, heading)
            pdf.ln(3)
            pdf.set_font("Helvetica", size=10)
            continue

        # H3
        if stripped.startswith("### "):
            heading = clean_md(stripped.lstrip("# "))
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, heading)
            pdf.set_font("Helvetica", size=10)
            continue

        # Regular text
        clean = clean_md(stripped)
        if not clean:
            continue

        # Always reset x to left margin before writing
        pdf.set_x(pdf.l_margin)
        try:
            pdf.multi_cell(w=0, h=line_h, text=clean, align="L")
        except Exception:
            # Skip problematic text — don't let it crash the whole PDF
            pdf.ln(line_h)

    pdf.output(str(pdf_path))
    size_kb = pdf_path.stat().st_size / 1024
    print(f"PDF created: {pdf_path} ({size_kb:.1f} KB)")
    return True


def upload_to_gumroad(pdf_path: Path) -> dict:
    """Upload product to Gumroad via API."""
    import requests

    if not GUMROAD_TOKEN:
        return {"error": "No GUMROAD_API_KEY in .env"}

    # 1. Check auth
    print("Checking Gumroad auth...")
    resp = requests.get(f"{API_BASE}/user", params={"access_token": GUMROAD_TOKEN})
    if resp.status_code != 200:
        return {"error": f"Auth failed: {resp.status_code} {resp.text[:200]}"}

    user = resp.json().get("user", {})
    print(f"Authenticated as: {user.get('name', 'unknown')} ({user.get('email', '?')})")

    # 2. Check existing products
    print("Checking existing products...")
    resp = requests.get(f"{API_BASE}/products", params={"access_token": GUMROAD_TOKEN})
    if resp.status_code == 200:
        products = resp.json().get("products", [])
        print(f"Found {len(products)} existing products")
        for p in products:
            if "AI Side Hustle" in p.get("name", "") or "ai-side-hustle" in p.get("custom_permalink", ""):
                print(f"Product already exists: {p.get('name')} (id={p.get('id')})")
                if not p.get("published"):
                    print("Enabling (publishing) existing product...")
                    enable_resp = requests.put(
                        f"{API_BASE}/products/{p['id']}",
                        data={"access_token": GUMROAD_TOKEN, "published": "true"},
                    )
                    if enable_resp.status_code == 200:
                        data = enable_resp.json()
                        url = data.get("product", {}).get("short_url", "")
                        print(f"PUBLISHED! URL: {url}")
                        return {"status": "published", "url": url, "id": p["id"]}
                url = p.get("short_url", "")
                return {"status": "already_exists", "id": p["id"], "url": url}

    # 3. Read listing description
    listing_text = LISTING_MD.read_text(encoding="utf-8") if LISTING_MD.exists() else ""
    short_desc = ""
    full_desc = ""
    if listing_text:
        sd_match = re.search(r"## 2\. SHORT DESCRIPTION\s*\n\n(.+?)(?=\n---|\n## )", listing_text, re.DOTALL)
        if sd_match:
            short_desc = sd_match.group(1).strip()
        fd_match = re.search(r"## 3\. FULL DESCRIPTION\s*\n\n---\s*\n(.+?)(?=\n---\s*\n## 4\.)", listing_text, re.DOTALL)
        if fd_match:
            full_desc = fd_match.group(1).strip()

    description = full_desc[:5000] if full_desc else short_desc[:2000]

    # 4. Create product via API
    print("Creating product on Gumroad...")
    product_data = {
        "access_token": GUMROAD_TOKEN,
        "name": "The AI Side Hustle Playbook: Start Earning with AI Tools in 30 Days",
        "price": 900,  # $9.00 in cents
        "description": description,
        "custom_permalink": "ai-side-hustle-playbook",
    }

    # Try with file upload
    files = None
    if pdf_path.exists():
        files = {"file": ("The_AI_Side_Hustle_Playbook.pdf", open(pdf_path, "rb"), "application/pdf")}

    resp = requests.post(f"{API_BASE}/products", data=product_data, files=files)
    print(f"Create response: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        if data.get("success"):
            product = data.get("product", {})
            product_id = product.get("id", "")
            print(f"Product created: {product.get('name')} (id={product_id})")

            # 5. Enable product
            if product_id:
                print("Publishing product...")
                enable_resp = requests.put(
                    f"{API_BASE}/products/{product_id}",
                    data={"access_token": GUMROAD_TOKEN, "published": "true"},
                )
                if enable_resp.status_code == 200 and enable_resp.json().get("success"):
                    url = enable_resp.json().get("product", {}).get("short_url", "")
                    print(f"PUBLISHED! URL: {url}")
                    return {"status": "published", "id": product_id, "url": url}

            return {"status": "created", "id": product_id, "url": product.get("short_url", "")}
        else:
            return {"error": f"API error: {data.get('message', 'unknown')}"}

    # Try to parse error response
    try:
        err_data = resp.json()
        err_msg = err_data.get("message", resp.text[:300])
    except Exception:
        err_msg = resp.text[:300]

    if resp.status_code == 404:
        print(f"Gumroad API returned 404. Response: {err_msg}")
        print("Product creation may not be supported via this API endpoint.")
        print(f"PDF is ready at: {pdf_path}")
        print("Manual upload URL: https://gumroad.com/products/new")
        return {"status": "api_no_create", "pdf_path": str(pdf_path), "note": err_msg}

    return {"error": f"HTTP {resp.status_code}: {err_msg}"}


def main():
    print("=" * 60)
    print("VITO: Uploading 'The AI Side Hustle Playbook' to Gumroad")
    print("=" * 60)

    if not EBOOK_MD.exists():
        print(f"ERROR: Ebook not found at {EBOOK_MD}")
        sys.exit(1)

    # Step 1: Convert to PDF
    print(f"\n1. Converting {EBOOK_MD.name} to PDF...")
    if not md_to_pdf(EBOOK_MD, EBOOK_PDF):
        print("ERROR: PDF conversion failed")
        sys.exit(1)

    # Step 2: Upload to Gumroad
    print("\n2. Uploading to Gumroad...")
    result = upload_to_gumroad(EBOOK_PDF)
    print(f"\nResult: {result}")

    # Summary
    print("\n" + "=" * 60)
    if result.get("status") in ("published", "created", "already_exists"):
        print(f"SUCCESS: Product is on Gumroad!")
        if result.get("url"):
            print(f"URL: {result['url']}")
    elif result.get("status") == "api_no_create":
        print("Gumroad API blocked product creation.")
        print(f"PDF ready at: {result.get('pdf_path', EBOOK_PDF)}")
    else:
        print(f"FAILED: {result.get('error', 'unknown error')}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    main()
