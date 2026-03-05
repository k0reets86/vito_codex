import pytest

from modules.workflow_recipe_executor import WorkflowRecipeExecutor


class _QueueOk:
    def __init__(self):
        self._id = 0

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        return self._id

    async def process_once(self):
        return {
            "job_id": self._id,
            "status": "done",
            "result": {"status": "published", "platform": "twitter", "url": "https://x.com/i/status/1", "tweet_id": "1"},
        }

    def list_jobs(self, limit=20):
        return [{"id": self._id, "status": "done", "evidence": "https://x.com/i/status/1"}]


class _QueueFail:
    def __init__(self):
        self._id = 0

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        return self._id

    async def process_once(self):
        return {"job_id": self._id, "status": "failed", "error": "boom"}

    def list_jobs(self, limit=20):
        return [{"id": self._id, "status": "failed", "last_error": "boom", "evidence": ""}]


@pytest.mark.asyncio
async def test_workflow_recipe_executor_accepts_on_required_evidence():
    exe = WorkflowRecipeExecutor(_QueueOk())
    out = await exe.run_once("twitter_publish", {"dry_run": True}, trace_id="t1")
    assert out["status"] == "accepted"
    assert out["platform"] == "twitter"


@pytest.mark.asyncio
async def test_workflow_recipe_executor_fails_when_job_failed():
    exe = WorkflowRecipeExecutor(_QueueFail())
    out = await exe.run_once("twitter_publish", {"dry_run": True}, trace_id="t2")
    assert out["status"] == "failed"
    assert "boom" in out["error"]

