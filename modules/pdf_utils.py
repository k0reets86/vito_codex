"""pdf_utils — minimal PDF creation from text (no external deps)."""

from __future__ import annotations

from pathlib import Path


def write_minimal_pdf(text: str, out_path: str) -> str:
    """Create a tiny PDF file with embedded plain text."""
    # Extremely minimal PDF with a single page and a text object.
    # This is not pretty, but valid for upload tests.
    lines = [line[:80] for line in text.splitlines() if line.strip()]
    if not lines:
        lines = ["(empty)"]
    content = "\\n".join(lines[:50])
    # Basic PDF structure
    pdf = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 5 0 R >>
stream
BT /F1 12 Tf 72 720 Td ({content}) Tj ET
endstream
endobj
5 0 obj
{len(content)+50}
endobj
6 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 7
0000000000 65535 f
0000000010 00000 n
0000000060 00000 n
0000000117 00000 n
0000000210 00000 n
0000000330 00000 n
0000000360 00000 n
trailer
<< /Size 7 /Root 1 0 R >>
startxref
420
%%EOF
"""
    Path(out_path).write_bytes(pdf.encode("latin-1", errors="ignore"))
    return out_path


def make_minimal_pdf(title: str, lines: list[str]) -> str:
    """Create a minimal PDF in output/products and return path."""
    out_dir = Path("/home/vito/vito-agent/output/products")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in title if c.isalnum() or c in ("-", "_"))[:60] or "product"
    out_path = out_dir / f"{safe}_minimal.pdf"
    text = title + "\n" + "\n".join(lines or [])
    return write_minimal_pdf(text, str(out_path))
