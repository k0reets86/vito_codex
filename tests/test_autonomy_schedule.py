from modules.autonomy_schedule import AutonomyScheduleState


def test_autonomy_schedule_state_due_and_mark(tmp_path):
    db = tmp_path / "test.sqlite"
    state = AutonomyScheduleState(sqlite_path=str(db))
    assert state.is_due("scout", current_tick=10, cadence_ticks=5) is True
    state.mark_run("scout", current_tick=10, cadence_ticks=5)
    assert state.is_due("scout", current_tick=12, cadence_ticks=5) is False
    assert state.is_due("scout", current_tick=15, cadence_ticks=5) is True
