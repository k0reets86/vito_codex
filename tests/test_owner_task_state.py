from modules.owner_task_state import OwnerTaskState


def test_owner_task_state_supports_metadata_and_enrich(tmp_path):
    state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    ok = state.set_active(
        "check amazon account",
        source="telegram",
        intent="goal_request",
        metadata={"service_context": "amazon_kdp"},
    )
    assert ok is True
    active = state.get_active()
    assert active["service_context"] == "amazon_kdp"
    changed = state.enrich_active(task_family="account_ops")
    assert changed is True
    active = state.get_active()
    assert active["task_family"] == "account_ops"
