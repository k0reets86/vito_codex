from modules.platform_knowledge import record_platform_lesson
from modules.platform_runbook_packs import build_runbook_packs_for_services, build_service_runbook_pack


def test_build_service_runbook_pack_includes_requirements_and_lessons():
    record_platform_lesson(
        "etsy",
        status="draft",
        summary="Draft updated",
        details="File and images attached",
        url="https://www.etsy.com/listing/123",
        lessons=["Reuse one working draft.", "Verify file after reload."],
        anti_patterns=["Do not publish during tests."],
        evidence={"listing_id": "123", "file_attached": True},
        source="test",
    )
    pack = build_service_runbook_pack("etsy")
    assert pack["service"] == "etsy"
    assert "main_file" in pack["required_artifacts"]
    assert "file_attached" in pack["evidence_keys_seen"]
    assert "Reuse one working draft." in pack["recommended_steps"]
    assert "Do not publish during tests." in pack["avoid_patterns"]
    assert isinstance(pack["policy_pack"], dict)
    assert "policy_notes" in pack
    assert "rules_updates" in pack


def test_build_runbook_packs_for_services_dedupes_aliases():
    packs = build_runbook_packs_for_services(["amazon", "kdp", "amazon_kdp", "etsy"])
    services = [p["service"] for p in packs]
    assert services.count("amazon_kdp") == 1
    assert "etsy" in services


def test_build_service_runbook_pack_includes_policy_pack():
    pack = build_service_runbook_pack("gumroad")
    assert pack["policy_pack"]["service"] == "gumroad"
    assert "has_policy_knowledge" in pack["policy_pack"]
    assert isinstance(pack["policy_notes"], list)
    assert isinstance(pack["rules_updates"], list)
