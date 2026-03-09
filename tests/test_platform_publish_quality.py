from modules.platform_publish_quality import validate_platform_publish_quality


def test_etsy_quality_gate_rejects_missing_file_proof():
    ok, errors = validate_platform_publish_quality(
        "etsy",
        {
            "status": "draft",
            "listing_id": "123",
            "screenshot_path": "runtime/etsy.png",
            "editor_audit": {"hasUploadPrompt": True, "imageCount": 2, "hasTags": True, "hasMaterials": True},
        },
        {"pdf_path": "/tmp/fake.pdf", "cover_path": "/tmp/c.png", "tags": ["a"], "materials": ["pdf guide"]},
    )
    assert ok is False
    assert "etsy_file_not_confirmed" in errors


def test_etsy_quality_gate_accepts_file_media_and_metadata_proof():
    ok, errors = validate_platform_publish_quality(
        "etsy",
        {
            "status": "draft",
            "listing_id": "123",
            "screenshot_path": "runtime/etsy.png",
            "file_attached": True,
            "image_count": 3,
            "tags_confirmed": True,
            "materials_confirmed": True,
            "editor_audit": {"hasUploadPrompt": False, "imageCount": 3, "hasTags": True, "hasMaterials": True},
        },
        {"pdf_path": "/tmp/fake.pdf", "cover_path": "/tmp/c.png", "tags": ["a"], "materials": ["pdf guide"]},
    )
    assert ok is True
    assert errors == []


def test_gumroad_quality_gate_rejects_missing_pdf():
    ok, errors = validate_platform_publish_quality(
        "gumroad",
        {
            "status": "draft",
            "draft_confirmed": True,
            "files_attached": ["cover.png"],
            "image_count": 1,
            "cover_confirmed": True,
            "preview_confirmed": True,
            "tags_confirmed": True,
        },
        {"pdf_path": "/tmp/fake.pdf", "cover_path": "/tmp/c.png"},
    )
    assert ok is False
    assert "gumroad_main_file_not_confirmed" in errors
