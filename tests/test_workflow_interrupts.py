from modules.workflow_interrupts import WorkflowInterrupts


def test_workflow_interrupts_open_and_list(tmp_path):
    db = str(tmp_path / "wf.db")
    wi = WorkflowInterrupts(sqlite_path=db)
    iid = wi.open_interrupt(
        goal_id="g1",
        interrupt_type="step_approval_pending",
        reason="owner_approval",
        step_num=2,
        thread_id="goal_g1",
        payload={"step": "publish"},
    )
    assert iid > 0
    rows = wi.list_interrupts(status="pending", limit=10)
    assert rows
    assert rows[0]["goal_id"] == "g1"
    assert rows[0]["status"] == "pending"


def test_workflow_interrupts_resolve(tmp_path):
    db = str(tmp_path / "wf.db")
    wi = WorkflowInterrupts(sqlite_path=db)
    wi.open_interrupt(goal_id="g2", interrupt_type="owner_approval_required", reason="budget")
    latest = wi.latest_pending("g2")
    assert latest is not None
    ok = wi.resolve_interrupt(int(latest["id"]), resolution="resumed")
    assert ok is True
    assert wi.latest_pending("g2") is None


def test_workflow_interrupts_resolve_pending_for_goal(tmp_path):
    db = str(tmp_path / "wf.db")
    wi = WorkflowInterrupts(sqlite_path=db)
    wi.open_interrupt(goal_id="g3", interrupt_type="step_approval_pending", reason="r1")
    wi.open_interrupt(goal_id="g3", interrupt_type="step_approval_pending", reason="r2")
    cnt = wi.resolve_pending_for_goal("g3", resolution="cancelled")
    assert cnt == 2
    rows = wi.list_interrupts(status="cancelled", limit=10)
    assert len(rows) == 2


def test_workflow_interrupts_latest_for_goal(tmp_path):
    db = str(tmp_path / "wf.db")
    wi = WorkflowInterrupts(sqlite_path=db)
    wi.open_interrupt(goal_id="g4", interrupt_type="step_approval_pending", reason="first")
    iid2 = wi.open_interrupt(goal_id="g4", interrupt_type="owner_approval_required", reason="second")
    latest = wi.latest_for_goal("g4")
    assert latest is not None
    assert int(latest["id"]) == iid2
    assert latest["interrupt_type"] == "owner_approval_required"


def test_workflow_interrupt_resume_events(tmp_path):
    db = str(tmp_path / "wf.db")
    wi = WorkflowInterrupts(sqlite_path=db)
    iid = wi.open_interrupt(goal_id="g5", interrupt_type="step_approval_pending", reason="approval")
    event_id = wi.log_resume_event("g5", iid, action="resumed", reason="auto_resume")
    assert event_id > 0
    assert wi.count_resume_events("g5", iid, action="resumed") == 1
    latest = wi.latest_resume_event("g5", iid, action="resumed")
    assert latest is not None
    assert latest["reason"] == "auto_resume"
    loaded_intr = wi.get_interrupt(iid)
    assert loaded_intr is not None
    assert loaded_intr["goal_id"] == "g5"


def test_workflow_interrupt_list_resume_events_filters(tmp_path):
    db = str(tmp_path / "wf.db")
    wi = WorkflowInterrupts(sqlite_path=db)
    i1 = wi.open_interrupt(goal_id="ga", interrupt_type="step_approval_pending", reason="approval")
    i2 = wi.open_interrupt(goal_id="gb", interrupt_type="owner_approval_required", reason="budget")
    wi.log_resume_event("ga", i1, action="resumed", reason="ok")
    wi.log_resume_event("ga", i1, action="skipped", reason="cooldown")
    wi.log_resume_event("gb", i2, action="cancelled", reason="owner")

    rows_goal = wi.list_resume_events(goal_id="ga", limit=10)
    assert len(rows_goal) == 2
    rows_action = wi.list_resume_events(action="cancelled", limit=10)
    assert len(rows_action) == 1
    assert rows_action[0]["goal_id"] == "gb"
    rows_intr = wi.list_resume_events(interrupt_id=i1, action="resumed", limit=10)
    assert len(rows_intr) == 1
    assert rows_intr[0]["reason"] == "ok"
