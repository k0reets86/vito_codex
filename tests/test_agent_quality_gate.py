from modules.agent_quality_gate import QUALITY_REQUIRED_ACTIONS, quality_gate


@quality_gate()
async def _default():
    return True


@quality_gate({"publish"})
async def _custom():
    return True


def test_quality_gate_default_marks_function():
    assert getattr(_default, "__quality_gate__", False) is True
    assert set(getattr(_default, "__quality_gate_actions__", [])) == set(QUALITY_REQUIRED_ACTIONS)


def test_quality_gate_custom_actions():
    assert getattr(_custom, "__quality_gate__", False) is True
    assert getattr(_custom, "__quality_gate_actions__", []) == ["publish"]
