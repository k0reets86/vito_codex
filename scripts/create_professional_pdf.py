#!/usr/bin/env python3
"""Create professional PDF ebook: The AI Side Hustle Playbook.

Uses reportlab for high-quality output with:
- Dark cover page
- Chapter headers with colored backgrounds
- Professional typography
- Bullet points with checkmarks
- CTA final page
"""

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Frame, PageTemplate, NextPageTemplate,
)
from reportlab.platypus.flowables import HRFlowable

EBOOK_MD = Path(__file__).resolve().parent.parent / "output/ebooks/ai_side_hustle_playbook.md"
OUTPUT_PDF = Path(__file__).resolve().parent.parent / "output/The_AI_Side_Hustle_Playbook_v2.pdf"

# Colors
DARK_BG = colors.HexColor("#0d1117")
CHAPTER_BG = colors.HexColor("#16213e")
ACCENT_GOLD = colors.HexColor("#FFD700")
ACCENT_BLUE = colors.HexColor("#4a90d9")
TEXT_WHITE = colors.HexColor("#ffffff")
TEXT_LIGHT = colors.HexColor("#c9d1d9")
TEXT_DARK = colors.HexColor("#1a1a2e")
BODY_TEXT = colors.HexColor("#2d2d2d")
SUBTLE_GRAY = colors.HexColor("#8b949e")
SECTION_BG = colors.HexColor("#f0f4f8")

W, H = letter
LEFT_M = 0.85 * inch
RIGHT_M = 0.85 * inch
TOP_M = 0.75 * inch
BOT_M = 0.75 * inch
CONTENT_W = W - LEFT_M - RIGHT_M


def _normalize_title(title: str) -> str:
    """Normalize title for dedup: extract chapter key or normalize text."""
    m = re.match(r"(Chapter \d+)", title)
    if m:
        return m.group(1)
    t = title.replace("\u2014", "-").replace("\u2013", "-").replace("  ", " ")
    return t.strip()


def parse_markdown(md_path: Path) -> list[dict]:
    """Parse markdown into structured sections."""
    text = md_path.read_text(encoding="utf-8")
    sections = []
    current_section = None
    seen_h1_normalized = set()

    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            if current_section and current_section["content"]:
                current_section["content"].append("")
            continue

        if stripped == "---":
            continue

        # H1 = chapter title
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped.lstrip("# ").strip()
            norm = _normalize_title(title)
            if norm in seen_h1_normalized:
                continue
            seen_h1_normalized.add(norm)
            if current_section:
                sections.append(current_section)
            current_section = {"type": "chapter", "title": title, "content": []}
            continue

        # H2 = sub-section
        if stripped.startswith("## "):
            if current_section:
                current_section["content"].append({"type": "h2", "text": stripped.lstrip("# ").strip()})
            continue

        # H3
        if stripped.startswith("### "):
            if current_section:
                current_section["content"].append({"type": "h3", "text": stripped.lstrip("# ").strip()})
            continue

        # Bold section header
        bold_match = re.match(r"^\*\*(.+)\*\*$", stripped)
        if bold_match and len(bold_match.group(1)) < 80:
            if current_section:
                current_section["content"].append({"type": "bold_header", "text": bold_match.group(1)})
            continue

        # Italic line
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            clean = stripped.strip("*").strip()
            if current_section:
                current_section["content"].append({"type": "italic", "text": clean})
            continue

        # Bullet items
        if stripped.startswith("- ") or stripped.startswith("* "):
            item_text = stripped[2:].strip()
            if current_section:
                current_section["content"].append({"type": "bullet", "text": item_text})
            continue

        # Regular paragraph
        clean = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", stripped)
        clean = re.sub(r"\*(.+?)\*", r"<i>\1</i>", clean)
        if current_section:
            current_section["content"].append({"type": "paragraph", "text": clean})

    if current_section:
        sections.append(current_section)

    return sections


def build_styles():
    """Create all paragraph styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "H2Style", parent=styles["Heading2"],
        fontSize=16, leading=22, textColor=ACCENT_BLUE,
        fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=8, leftIndent=0,
    ))

    styles.add(ParagraphStyle(
        "BoldHeader", parent=styles["Heading3"],
        fontSize=13, leading=18, textColor=TEXT_DARK,
        fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        "BodyText2", parent=styles["Normal"],
        fontSize=10.5, leading=16, textColor=BODY_TEXT,
        fontName="Helvetica", alignment=TA_JUSTIFY,
        spaceBefore=2, spaceAfter=6, firstLineIndent=0,
    ))

    styles.add(ParagraphStyle(
        "BulletStyle", parent=styles["Normal"],
        fontSize=10.5, leading=16, textColor=BODY_TEXT,
        fontName="Helvetica", leftIndent=24, spaceBefore=2, spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        "ItalicStyle", parent=styles["Normal"],
        fontSize=10.5, leading=16, textColor=SUBTLE_GRAY,
        fontName="Helvetica-Oblique", alignment=TA_CENTER,
        spaceBefore=4, spaceAfter=8,
    ))

    return styles


# === Page drawing callbacks ===

def draw_cover(canvas, doc):
    """Draw dark cover page with title, subtitle, tagline."""
    canvas.saveState()

    canvas.setFillColor(DARK_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

    # Top gold line
    canvas.setStrokeColor(ACCENT_GOLD)
    canvas.setLineWidth(2)
    y_top = H - 2.0 * inch
    canvas.line(1.5 * inch, y_top, W - 1.5 * inch, y_top)

    # Title
    canvas.setFillColor(TEXT_WHITE)
    canvas.setFont("Helvetica-Bold", 36)
    title_y = H - 3.0 * inch
    canvas.drawCentredString(W / 2, title_y, "The AI Side Hustle")
    canvas.drawCentredString(W / 2, title_y - 44, "Playbook")

    # Subtitle
    canvas.setFillColor(ACCENT_GOLD)
    canvas.setFont("Helvetica", 17)
    sub_y = title_y - 100
    canvas.drawCentredString(W / 2, sub_y, "Start Earning with AI Tools in 30 Days")

    # Tagline
    canvas.setFillColor(TEXT_LIGHT)
    canvas.setFont("Helvetica-Oblique", 11)
    tag_y = sub_y - 30
    canvas.drawCentredString(W / 2, tag_y, "A practical guide to building your first AI-powered income stream")

    # Line below subtitle
    canvas.setStrokeColor(ACCENT_BLUE)
    canvas.setLineWidth(1)
    canvas.line(2.5 * inch, tag_y - 20, W - 2.5 * inch, tag_y - 20)

    # Bottom
    canvas.setFillColor(SUBTLE_GRAY)
    canvas.setFont("Helvetica", 12)
    canvas.drawCentredString(W / 2, 1.5 * inch, "2026 Edition")

    canvas.setFillColor(ACCENT_BLUE)
    canvas.setFont("Helvetica", 10)
    canvas.drawCentredString(W / 2, 1.1 * inch, "tarasovbusiness.gumroad.com")

    canvas.restoreState()


def draw_content_page(canvas, doc):
    """Draw footer on regular content pages."""
    canvas.saveState()

    canvas.setFillColor(SUBTLE_GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(W / 2, 0.4 * inch, f"The AI Side Hustle Playbook  |  Page {doc.page - 1}")

    # Thin top line
    canvas.setStrokeColor(colors.HexColor("#e0e0e0"))
    canvas.setLineWidth(0.5)
    canvas.line(LEFT_M, H - 0.5 * inch, W - RIGHT_M, H - 0.5 * inch)

    canvas.restoreState()


def draw_cta_page(canvas, doc):
    """Draw dark CTA final page."""
    canvas.saveState()

    canvas.setFillColor(DARK_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

    # Gold line
    y = H - 2.5 * inch
    canvas.setStrokeColor(ACCENT_GOLD)
    canvas.setLineWidth(2)
    canvas.line(2 * inch, y, W - 2 * inch, y)

    # Title
    canvas.setFillColor(ACCENT_GOLD)
    canvas.setFont("Helvetica-Bold", 32)
    canvas.drawCentredString(W / 2, y - 50, "Ready to Start?")

    # Body
    canvas.setFillColor(TEXT_WHITE)
    canvas.setFont("Helvetica", 14)
    lines = [
        "You've read the playbook. You know the hustles.",
        "You have the tools and the 30-day plan.",
        "",
        "The only thing left is to begin.",
    ]
    text_y = y - 100
    for line in lines:
        canvas.drawCentredString(W / 2, text_y, line)
        text_y -= 24

    # CTA link
    text_y -= 20
    canvas.setFillColor(ACCENT_GOLD)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawCentredString(W / 2, text_y, "Start your AI side hustle today:")
    text_y -= 30
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawCentredString(W / 2, text_y, "tarasovbusiness.gumroad.com")

    # Bottom line
    canvas.setStrokeColor(ACCENT_BLUE)
    canvas.setLineWidth(1)
    canvas.line(2.5 * inch, 1.5 * inch, W - 2.5 * inch, 1.5 * inch)

    # Footer
    canvas.setFillColor(SUBTLE_GRAY)
    canvas.setFont("Helvetica", 9)
    canvas.drawCentredString(W / 2, 1.2 * inch, "The AI Side Hustle Playbook | 2026 Edition")
    canvas.drawCentredString(W / 2, 1.0 * inch, "Start today. Your AI side hustle is waiting.")

    canvas.restoreState()


def create_pdf(sections: list[dict], output_path: Path):
    """Build the PDF document."""
    styles = build_styles()

    # Content frame (same for all page templates)
    content_frame = Frame(LEFT_M, BOT_M, CONTENT_W, H - TOP_M - BOT_M, id="normal")

    # Page templates
    cover_template = PageTemplate(id="cover", frames=[content_frame], onPage=draw_cover)
    content_template = PageTemplate(id="content", frames=[content_frame], onPage=draw_content_page)
    cta_template = PageTemplate(id="cta", frames=[content_frame], onPage=draw_cta_page)

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=letter,
        pageTemplates=[cover_template, content_template, cta_template],
    )

    story = []

    # Cover page: switch to content template after first page
    story.append(NextPageTemplate("content"))
    story.append(PageBreak())

    chapter_num = 0

    for section in sections:
        title = section["title"]

        ch_match = re.match(r"Chapter (\d+)[:\u2014]", title)
        if ch_match:
            chapter_num = int(ch_match.group(1))
        elif "About This Book" in title:
            chapter_num = 0
        else:
            chapter_num = 0

        # Page break before each chapter
        story.append(PageBreak())

        # Chapter header
        if chapter_num > 0:
            ch_title_text = re.sub(r"^Chapter \d+[:\u2014]\s*", "", title).strip()
            ch_label = f'<font color="#4a90d9" size="42"><b>{chapter_num}</b></font>'
            ch_title_para = Paragraph(
                f'<font color="#ffffff" size="18"><b>{ch_title_text}</b></font>',
                ParagraphStyle("_ch", parent=styles["Normal"], leading=24, alignment=TA_LEFT),
            )
            header_data = [[Paragraph(ch_label, styles["Normal"]), ch_title_para]]
            header_table = Table(header_data, colWidths=[0.8 * inch, CONTENT_W - 0.8 * inch])
            header_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), CHAPTER_BG),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 15),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
                ("RIGHTPADDING", (-1, -1), (-1, -1), 15),
                ("TOPPADDING", (0, 0), (-1, -1), 18),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
            ]))
            story.append(header_table)
            story.append(Spacer(1, 8))
            story.append(HRFlowable(
                width="100%", thickness=2, color=ACCENT_GOLD,
                spaceBefore=0, spaceAfter=10,
            ))
        else:
            story.append(Paragraph(
                f'<font color="#1a1a2e" size="20"><b>{title}</b></font>',
                styles["BoldHeader"],
            ))
            story.append(Spacer(1, 10))

        # Content items
        for item in section["content"]:
            if isinstance(item, str):
                if not item:
                    story.append(Spacer(1, 4))
                continue

            itype = item.get("type", "")
            text = item.get("text", "")

            if itype == "h2":
                h2_data = [[Paragraph(
                    f'<font color="#4a90d9"><b>{text}</b></font>', styles["H2Style"],
                )]]
                h2_table = Table(h2_data, colWidths=[CONTENT_W])
                h2_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), SECTION_BG),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT_BLUE),
                ]))
                story.append(Spacer(1, 8))
                story.append(h2_table)
                story.append(Spacer(1, 6))

            elif itype == "bold_header":
                bh_data = [[Paragraph(
                    f'<font color="#1a1a2e"><b>{text}</b></font>', styles["BoldHeader"],
                )]]
                bh_table = Table(bh_data, colWidths=[CONTENT_W])
                bh_table.setStyle(TableStyle([
                    ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT_BLUE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(Spacer(1, 6))
                story.append(bh_table)
                story.append(Spacer(1, 3))

            elif itype == "h3":
                story.append(Spacer(1, 4))
                story.append(Paragraph(f'<b>{text}</b>', styles["BoldHeader"]))

            elif itype == "bullet":
                clean_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
                clean_text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", clean_text)
                bullet_html = (
                    '<font name="ZapfDingbats" color="#4a90d9" size="10">4</font>'
                    f'&nbsp;&nbsp;{clean_text}'
                )
                story.append(Paragraph(bullet_html, styles["BulletStyle"]))

            elif itype == "italic":
                story.append(Paragraph(f'<i>{text}</i>', styles["ItalicStyle"]))

            elif itype == "paragraph":
                story.append(Paragraph(text, styles["BodyText2"]))

    # CTA page
    story.append(NextPageTemplate("cta"))
    story.append(PageBreak())
    story.append(Spacer(1, 1))  # Minimal content to trigger the page

    doc.build(story)

    size_kb = output_path.stat().st_size / 1024
    print(f"PDF created: {output_path}")
    print(f"Size: {size_kb:.1f} KB")
    return True


def main():
    print("=" * 60)
    print("Creating professional PDF: The AI Side Hustle Playbook v2")
    print("=" * 60)

    if not EBOOK_MD.exists():
        print(f"ERROR: Source not found: {EBOOK_MD}")
        return False

    print(f"\nParsing markdown...")
    sections = parse_markdown(EBOOK_MD)
    print(f"Found {len(sections)} sections:")
    for s in sections:
        content_items = len([c for c in s["content"] if isinstance(c, dict)])
        print(f"  - {s['title'][:60]} ({content_items} items)")

    print(f"\nBuilding PDF...")
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    result = create_pdf(sections, OUTPUT_PDF)

    if result:
        print(f"\nSUCCESS: {OUTPUT_PDF}")
    return result


if __name__ == "__main__":
    main()
