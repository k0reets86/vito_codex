from modules.workflow_state_machine import WorkflowStateMachine


def test_workflow_transitions_and_checkpoint(tmp_path):
    db = str(tmp_path / "wf.db")
    wf = WorkflowStateMachine(sqlite_path=db)
    trace = wf.start_or_attach("g1")
    assert trace.startswith("wf_")
    assert wf.get_state("g1") == "created"

    ok, _ = wf.transition("g1", "planning", reason="test")
    assert ok
    ok, _ = wf.transition("g1", "executing", reason="test")
    assert ok
    wf.checkpoint_step("g1", 1, "completed", detail="ok")
    ok, _ = wf.transition("g1", "learning", reason="test")
    assert ok
    ok, _ = wf.transition("g1", "completed", reason="test")
    assert ok
    assert wf.get_state("g1") == "completed"
    ev = wf.recent_events("g1", limit=10)
    assert len(ev) >= 5
    ck = wf.latest_checkpoint("g1")
    assert ck is not None
    assert ck["step_num"] == 1
    assert ck["status"] == "completed"


def test_invalid_transition_rejected(tmp_path):
    db = str(tmp_path / "wf2.db")
    wf = WorkflowStateMachine(sqlite_path=db)
    wf.start_or_attach("g2")
    ok, _ = wf.transition("g2", "completed", reason="invalid_direct")
    assert not ok
    assert wf.get_state("g2") == "created"
