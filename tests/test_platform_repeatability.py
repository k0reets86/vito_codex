from modules.platform_repeatability import attach_analytics_repeatability, attach_publish_repeatability


def test_attach_publish_repeatability_marks_artifacts():
    result = attach_publish_repeatability(
        {"platform": "medium", "status": "draft", "story_id": "abc", "url": "https://x"},
        platform="medium",
        mode="api",
        artifact_flags={"story_id": True, "url": True},
    )
    profile = result["repeatability_profile"]
    assert profile["platform"] == "medium"
    assert profile["repeatability_grade"] == "strong"
    assert "story_id" in profile["confirmed_artifacts"]


def test_attach_analytics_repeatability_marks_source():
    result = attach_analytics_repeatability(
        {"platform": "shopify", "status": "ok", "raw_data": {"value": 1}},
        platform="shopify",
        source="browser_admin",
    )
    assert result["repeatability_profile"]["source"] == "browser_admin"
    assert result["repeatability_profile"]["repeatability_grade"] == "strong"
