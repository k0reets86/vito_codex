from pathlib import Path

from modules.publish_contract import build_publish_signature, validate_publish_payload


def test_validate_publish_payload_ok(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    cover = tmp_path / "cover.png"
    thumb = tmp_path / "thumb.png"
    pdf.write_bytes(b"%PDF-1.4 test")
    cover.write_bytes(b"png")
    thumb.write_bytes(b"png")

    ok, errors, norm = validate_publish_payload(
        "gumroad",
        {
            "name": "Test Product 1",
            "description": "This is a sufficiently long product description for validation.",
            "price": 5,
            "pdf_path": str(pdf),
            "cover_path": str(cover),
            "thumb_path": str(thumb),
            "category": "Programming",
            "tags": ["ai", "automation"],
            "draft_only": False,
        },
    )
    assert ok is True
    assert errors == []
    assert norm["price"] == 5


def test_validate_publish_payload_missing_fields(tmp_path: Path):
    ok, errors, _ = validate_publish_payload(
        "gumroad",
        {"name": "x", "description": "short", "price": 0, "draft_only": False},
    )
    assert ok is False
    assert "invalid_name" in errors
    assert "invalid_description" in errors
    assert "invalid_price" in errors
    assert "missing_pdf" in errors
    assert "missing_cover" in errors
    assert "missing_thumb" in errors
    assert "missing_category" in errors
    assert "missing_tags" in errors


def test_signature_stable_for_same_payload(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    cover = tmp_path / "cover.png"
    thumb = tmp_path / "thumb.png"
    pdf.write_bytes(b"%PDF-1.4 test")
    cover.write_bytes(b"png")
    thumb.write_bytes(b"png")
    payload = {
        "name": "Product",
        "description": "A" * 80,
        "price": 5,
        "pdf_path": str(pdf),
        "cover_path": str(cover),
        "thumb_path": str(thumb),
        "category": "Programming",
        "tags": ["automation", "ai"],
    }
    s1 = build_publish_signature("gumroad", payload)
    s2 = build_publish_signature("gumroad", payload)
    assert s1 == s2
    assert len(s1) == 16
