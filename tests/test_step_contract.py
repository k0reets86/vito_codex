from modules.step_contract import validate_step_output, validate_step_result


def test_validate_step_output_accepts_tooling_dry_run_status():
    chk = validate_step_output({"status": "dry_run", "adapter_key": "demo"})
    assert chk.ok is True


def test_validate_step_result_completed_requires_output():
    chk = validate_step_result({"status": "completed"})
    assert chk.ok is False
    assert "result_output_missing" in chk.errors


def test_validate_step_result_waiting_approval_requires_error():
    chk = validate_step_result({"status": "waiting_approval"})
    assert chk.ok is False
    assert "result_error_missing" in chk.errors


def test_validate_step_result_completed_publish_without_evidence():
    chk = validate_step_result(
        {"status": "completed", "output": {"status": "published", "platform": "threads"}}
    )
    assert chk.ok is False
    assert any(e.startswith("output:") for e in chk.errors)
