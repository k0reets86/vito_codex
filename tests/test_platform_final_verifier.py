from modules.platform_final_verifier import verify_platform_result


def test_final_verifier_rejects_success_without_evidence():
    out = verify_platform_result(
        "twitter",
        {"platform": "twitter", "status": "published"},
        {"text": "hello"},
    )
    assert out.ok is False
    assert any("platform_contract_invalid:success_without_evidence" == e for e in out.errors)


def test_final_verifier_rejects_etsy_partial_draft():
    out = verify_platform_result(
        "etsy",
        {
            "platform": "etsy",
            "status": "draft",
            "listing_id": "123",
            "url": "https://www.etsy.com/listing/123",
            "screenshot_path": "runtime/etsy.png",
            "editor_audit": {"hasUploadPrompt": True, "image_count": 2, "hasTags": True, "hasMaterials": True},
        },
        {"pdf_path": "/tmp/fake.pdf", "tags": ["a"], "materials": ["pdf guide"]},
    )
    assert out.ok is False
    assert any("publish_quality_gate_failed:etsy_file_not_confirmed" == e for e in out.errors)


def test_final_verifier_accepts_confirmed_gumroad_result():
    out = verify_platform_result(
        "gumroad",
        {
            "platform": "gumroad",
            "status": "published",
            "url": "https://gumroad.com/l/ok",
            "id": "g1",
            "main_file_attached": True,
            "cover_confirmed": True,
            "preview_confirmed": True,
            "thumbnail_confirmed": True,
            "tags_confirmed": True,
            "image_count": 2,
        },
        {"pdf_path": "/tmp/fake.pdf", "cover_path": "/tmp/cover.png", "tags": ["a"]},
    )
    assert out.ok is True
    assert out.errors == []
