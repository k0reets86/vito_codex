from modules.platform_result_contract import (
    normalize_platform_result,
    validate_platform_result_contract,
)


def test_platform_result_contract_success_requires_evidence():
    payload = normalize_platform_result({"status": "published", "platform": "twitter"}, platform="twitter")
    chk = validate_platform_result_contract(payload, require_evidence_for_success=True)
    assert chk.ok is False
    assert "success_without_evidence" in chk.errors


def test_platform_result_contract_success_with_evidence_ok():
    payload = normalize_platform_result(
        {"status": "published", "platform": "twitter", "url": "https://x.com/i/status/1"},
        platform="twitter",
    )
    chk = validate_platform_result_contract(payload, require_evidence_for_success=True)
    assert chk.ok is True

