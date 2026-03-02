from datetime import datetime, timedelta, timezone
import sqlite3

from modules.schedule_manager import ScheduleManager


def _past_iso(minutes: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def test_acquire_due_tasks_claims_once(tmp_path):
    db = str(tmp_path / "sched.db")
    m1 = ScheduleManager(sqlite_path=db)
    m2 = ScheduleManager(sqlite_path=db)

    m1.add_task(
        title="daily report",
        action="report",
        schedule_type="once",
        run_at=_past_iso(2),
    )

    due1 = m1.acquire_due_tasks(owner="worker-1", limit=10, lock_minutes=10)
    due2 = m2.acquire_due_tasks(owner="worker-2", limit=10, lock_minutes=10)

    assert len(due1) == 1
    assert len(due2) == 0
    assert due1[0].status == "running"

    m1.mark_run(due1[0])
    tasks = m1.list_tasks()
    assert tasks[0].status == "done"


def test_acquire_due_tasks_reclaims_stale_lock(tmp_path):
    db = str(tmp_path / "sched_stale.db")
    m1 = ScheduleManager(sqlite_path=db)
    m2 = ScheduleManager(sqlite_path=db)

    tid = m1.add_task(
        title="stale task",
        action="reminder",
        schedule_type="once",
        run_at=_past_iso(5),
    )

    claimed = m1.acquire_due_tasks(owner="worker-1", limit=10, lock_minutes=10)
    assert len(claimed) == 1

    # Simulate crashed worker: task remains running with expired lease.
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET status = 'running', run_lock_owner = 'worker-1', run_lock_until = ?
            WHERE id = ?
            """,
            (_past_iso(1), tid),
        )
        conn.commit()
    finally:
        conn.close()

    reclaimed = m2.acquire_due_tasks(owner="worker-2", limit=10, lock_minutes=10)
    assert len(reclaimed) == 1
    assert reclaimed[0].id == tid
    assert reclaimed[0].status == "running"
