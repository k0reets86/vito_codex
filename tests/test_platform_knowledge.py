from modules.platform_knowledge import get_service_knowledge, record_platform_lesson


def test_record_platform_lesson_persists_service_knowledge():
    record_platform_lesson(
        "gumroad",
        status="draft",
        summary="Draft updated",
        details="PDF attached, tags pending",
        url="https://gumroad.com/l/test-slug",
        lessons=["Reuse one working draft."],
        anti_patterns=["Do not create duplicate drafts."],
        evidence={"slug": "test-slug"},
        source="test",
    )
    data = get_service_knowledge("gumroad")
    assert isinstance(data, dict)
    assert "success_runbooks" in data
    assert data["success_runbooks"]
    last = data["success_runbooks"][-1]
    assert last["status"] == "draft"
    assert "Reuse one working draft." in last["lessons"]
