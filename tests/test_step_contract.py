from modules.step_contract import validate_step_output


def test_step_contract_accepts_text_and_evidence_dict():
    r1 = validate_step_output("ok text")
    assert r1.ok

    r2 = validate_step_output({"status": "published", "url": "https://example.com/x"})
    assert r2.ok


def test_step_contract_rejects_publish_without_evidence():
    r = validate_step_output({"status": "published", "platform": "gumroad"})
    assert not r.ok
    assert "publish_without_evidence" in r.errors
