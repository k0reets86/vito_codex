from modules.owner_task_state import OwnerTaskState


def test_owner_task_state_set_and_complete(tmp_path):
    st = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    ok = st.set_active("сделать отчёт", intent="goal_request")
    assert ok is True
    active = st.get_active()
    assert active is not None
    assert "отчёт" in active.get("text", "")
    st.complete("done")
    assert st.get_active() is None


def test_owner_task_state_cancel(tmp_path):
    st = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    st.set_active("запустить публикацию", intent="system_action")
    st.cancel("owner_cancelled")
    assert st.get_active() is None


def test_owner_task_state_does_not_overwrite_without_force(tmp_path):
    st = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    assert st.set_active("первая задача", intent="goal_request") is True
    assert st.set_active("вторая задача", intent="goal_request") is False
    active = st.get_active()
    assert active is not None
    assert "первая" in active.get("text", "")
    assert st.set_active("вторая задача", intent="manual_replace", force=True) is True
    active2 = st.get_active()
    assert "вторая" in str(active2.get("text", ""))
