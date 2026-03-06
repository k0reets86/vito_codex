from modules.platform_artifact_pack import build_platform_bundle, get_platform_pack


def test_platform_pack_exists_for_core_platforms():
    for p in ("gumroad", "etsy", "kofi", "amazon_kdp", "twitter", "reddit", "pinterest", "printful"):
        pack = get_platform_pack(p)
        assert pack is not None
        assert pack.platform == p
        assert len(pack.required_fields) >= 1


def test_build_bundle_gumroad_has_required_keys():
    out = build_platform_bundle("gumroad", {"title": "VITO Bundle Test", "description": "Test description", "price": 5})
    for k in ("name", "description", "price", "category", "tags", "cover_path", "thumb_path", "pdf_path"):
        assert k in out
    assert isinstance(out.get("tags"), list)


def test_build_bundle_social_has_text_and_image():
    tw = build_platform_bundle("twitter", {"text": "hello"})
    rd = build_platform_bundle("reddit", {"title": "hello", "subreddit": "test"})
    pn = build_platform_bundle("pinterest", {"title": "hello", "url": "https://example.com"})
    assert "text" in tw
    assert "title" in rd and "subreddit" in rd
    assert "title" in pn and "url" in pn

