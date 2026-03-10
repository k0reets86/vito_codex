from modules.platform_live_validation import validate_owner_grade_repeatability
from modules.platform_repeatability import attach_analytics_repeatability, attach_publish_repeatability


def test_attach_publish_repeatability_marks_artifacts():
    result = attach_publish_repeatability(
        {"platform": "medium", "status": "draft", "story_id": "abc", "url": "https://x", "screenshot_path": "/tmp/x.png"},
        platform="medium",
        mode="api",
        artifact_flags={"story_id": True, "url": True, "screenshot": True},
        required_artifacts=("story_id", "url", "screenshot"),
    )
    profile = result["repeatability_profile"]
    assert profile["platform"] == "medium"
    assert profile["repeatability_grade"] == "owner_grade"
    assert "story_id" in profile["confirmed_artifacts"]
    assert profile["owner_grade_ready"] is True
    ok, errors = validate_owner_grade_repeatability(result)
    assert ok is True
    assert errors == []


def test_attach_publish_repeatability_marks_missing_required():
    result = attach_publish_repeatability(
        {"platform": "etsy", "status": "draft", "listing_id": "123", "url": "https://www.etsy.com/listing/123"},
        platform="etsy",
        mode="browser",
        artifact_flags={"file": True, "images": False},
        required_artifacts=("file", "images"),
    )
    profile = result["repeatability_profile"]
    assert profile["repeatability_grade"] == "partial"
    assert profile["owner_grade_ready"] is False
    assert profile["missing_required_artifacts"] == ["images"]
    ok, errors = validate_owner_grade_repeatability(result)
    assert ok is False
    assert "owner_grade_not_ready" in errors


def test_attach_analytics_repeatability_marks_source():
    result = attach_analytics_repeatability(
        {"platform": "shopify", "status": "ok", "raw_data": {"value": 1}},
        platform="shopify",
        source="browser_admin",
    )
    assert result["repeatability_profile"]["source"] == "browser_admin"
    assert result["repeatability_profile"]["repeatability_grade"] == "strong"
