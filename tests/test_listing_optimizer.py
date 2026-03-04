from modules.listing_optimizer import get_platform_spec, optimize_listing_payload


def test_optimize_listing_payload_gumroad_defaults():
    out = optimize_listing_payload(
        "gumroad",
        {
            "title": "AI Prompt Pack",
            "description": "Prompt pack for creators.",
            "price": 9,
        },
    )
    assert out["name"]
    assert out["category"]
    assert isinstance(out["tags"], list) and len(out["tags"]) >= 3
    assert len(out["tags"]) <= get_platform_spec("gumroad")["tags_max"]
    assert out["short_description"]
    assert out["seo_title"]
    assert out["seo_description"]
    assert "seo_score" in out
    assert isinstance(out["publish_ready"], bool)


def test_optimize_listing_payload_etsy_tag_limit():
    out = optimize_listing_payload(
        "etsy",
        {
            "title": "Notion Finance Planner",
            "description": "A" * 400,
            "tags": [f"tag{i}" for i in range(25)],
        },
    )
    spec = get_platform_spec("etsy")
    assert len(out["tags"]) <= spec["tags_max"]
    assert all(len(t) <= spec["tag_max_len"] for t in out["tags"])

