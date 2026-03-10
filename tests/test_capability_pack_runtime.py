from modules.capability_pack_runtime import error_result, missing_fields, success_result


def test_missing_fields_detects_empty_values():
    missing = missing_fields({"a": "x", "b": "", "c": None}, ["a", "b", "c"])
    assert missing == ["b", "c"]


def test_success_result_builds_runtime_structure():
    out = success_result(
        "demo",
        output={"foo": "bar"},
        evidence={"id": "demo:1"},
        next_actions=["next"],
        recovery_hints=["retry"],
    )
    assert out["status"] == "ok"
    assert out["output"]["capability"] == "demo"
    assert out["output"]["verification_ok"] is True
    assert out["output"]["evidence"]["id"] == "demo:1"


def test_error_result_contains_recovery_shape():
    out = error_result("missing", capability="demo", missing=["field_a"])
    assert out["status"] == "error"
    assert out["output"]["verification_ok"] is False
    assert "provide:field_a" in out["output"]["next_actions"]

