from modules.workflow_threads import WorkflowThreads


def test_workflow_threads_crud(tmp_path):
    db = str(tmp_path / "threads.db")
    wt = WorkflowThreads(sqlite_path=db)
    wt.start_thread("t1", goal_id="g1")
    wt.update_thread("t1", status="executing", last_node="step_1")
    row = wt.get_thread("t1")
    assert row["thread_id"] == "t1"
    assert row["goal_id"] == "g1"
    assert row["status"] == "executing"
    rows = wt.list_threads(limit=10)
    assert len(rows) >= 1
