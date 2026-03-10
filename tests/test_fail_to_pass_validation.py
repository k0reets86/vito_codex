from __future__ import annotations

import asyncio

from modules.fail_to_pass_validation import run_fail_to_pass_validation


def test_fail_to_pass_validation(tmp_path):
    result = asyncio.run(run_fail_to_pass_validation(tmp_path))
    assert result["baseline_failed"] is True
    assert result["patched_passed"] is True
    assert result["baseline_snapshot"]
    assert result["patched_snapshot"]
