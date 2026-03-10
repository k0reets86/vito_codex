from modules.platform_target_registry import (
    remember_platform_working_target,
    target_identity,
    working_target_matches_task,
)


def test_target_identity_extracts_known_fields() -> None:
    ident = target_identity({"listing_id": "123", "slug": "abc", "url": "https://x"})
    assert ident["target_slug"] == "abc"
    assert ident["url"] == "https://x"


def test_working_target_matches_task_requires_same_root() -> None:
    current = {
        "id": "123",
        "task_root_id": "root-1",
        "mutable": True,
        "platform": "etsy",
    }
    assert working_target_matches_task(current, "root-1") is True
    assert working_target_matches_task(current, "root-2") is False


def test_remember_platform_working_target_sets_lock_for_published(tmp_path, monkeypatch) -> None:
    from modules import platform_target_registry as reg

    monkeypatch.setattr(reg, "_WORKING_PLATFORM_TARGETS", tmp_path / "working.json")
    monkeypatch.setattr(reg, "_PROTECTED_PLATFORM_TARGETS", tmp_path / "protected.json")
    remember_platform_working_target(
        "gumroad",
        {"slug": "abc123", "url": "https://gumroad.com/l/abc123", "status": "published", "task_root_id": "root-x"},
    )
    data = reg.load_working_platform_targets()
    assert data["gumroad"]["target_slug"] == "abc123"
    assert data["gumroad"]["mutable"] is False
    assert data["gumroad"]["locked"] is True
