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
