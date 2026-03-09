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


class _QueuePreparedReddit:
    def __init__(self):
        self._id = 0

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        return self._id

    async def process_once(self):
        return {
            "job_id": self._id,
            "status": "done",
            "result": {
                "status": "prepared",
                "platform": "reddit",
                "url": "https://www.reddit.com/user/demo/submit/?type=TEXT",
            },
        }

    def list_jobs(self, limit=20):
        return [{"id": self._id, "status": "done", "evidence": "https://www.reddit.com/user/demo/submit/?type=TEXT"}]


class _QueueKdpPrepared:
    def __init__(self):
        self._id = 0

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        return self._id

    async def process_once(self):
        return {
            "job_id": self._id,
            "status": "done",
            "result": {
                "status": "prepared",
                "platform": "amazon_kdp",
                "output": {"fields_filled": 0},
            },
        }

    def list_jobs(self, limit=20):
        return [{"id": self._id, "status": "done", "evidence": ""}]


class _QueueEtsyDraftNoScreenshot:
    def __init__(self):
        self._id = 0

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        return self._id

    async def process_once(self):
        return {
            "job_id": self._id,
            "status": "done",
            "result": {
                "status": "draft",
                "platform": "etsy",
                "listing_id": "123",
                "url": "https://www.etsy.com/listing/123",
            },
        }

    def list_jobs(self, limit=20):
        return [{"id": self._id, "status": "done", "evidence": "https://www.etsy.com/listing/123"}]


class _QueueKdpDraftWithEvidence:
    def __init__(self):
        self._id = 0

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        return self._id

    async def process_once(self):
        return {
            "job_id": self._id,
            "status": "done",
            "result": {
                "status": "draft",
                "platform": "amazon_kdp",
                "screenshot_path": "runtime/kdp.png",
                "output": {"fields_filled": 3},
            },
        }

    def list_jobs(self, limit=20):
        return [{"id": self._id, "status": "done", "evidence": "runtime/kdp.png"}]


class _QueueEtsyDraftWithScreenshotButNoFileProof:
    def __init__(self):
        self._id = 0

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        return self._id

    async def process_once(self):
        return {
            "job_id": self._id,
            "status": "done",
            "result": {
                "status": "draft",
                "platform": "etsy",
                "listing_id": "123",
                "url": "https://www.etsy.com/listing/123",
                "screenshot_path": "runtime/etsy.png",
                "editor_audit": {"hasUploadPrompt": True, "image_count": 2, "hasTags": True, "hasMaterials": True},
            },
        }

    def list_jobs(self, limit=20):
        return [{"id": self._id, "status": "done", "evidence": "runtime/etsy.png"}]


@pytest.mark.asyncio
async def test_workflow_recipe_executor_accepts_on_required_evidence():
    exe = WorkflowRecipeExecutor(_QueueOk())
    out = await exe.run_once("twitter_publish", {"dry_run": False}, trace_id="t1")
    assert out["status"] == "accepted"
    assert out["platform"] == "twitter"


@pytest.mark.asyncio
async def test_workflow_recipe_executor_fails_when_job_failed():
    exe = WorkflowRecipeExecutor(_QueueFail())
    out = await exe.run_once("twitter_publish", {"dry_run": True}, trace_id="t2")
    assert out["status"] == "failed"
    assert "boom" in out["error"]


@pytest.mark.asyncio
async def test_workflow_recipe_executor_rejects_prepared_reddit_submit_url():
    exe = WorkflowRecipeExecutor(_QueuePreparedReddit())
    out = await exe.run_once("reddit_publish", {"dry_run": False}, trace_id="t3")
    assert out["status"] == "failed"
    assert "status_not_accepted" in out["error"]


@pytest.mark.asyncio
async def test_workflow_recipe_executor_rejects_kdp_when_no_fields_filled():
    exe = WorkflowRecipeExecutor(_QueueKdpPrepared())
    out = await exe.run_once("kdp_publish", {"dry_run": False}, trace_id="t4")
    assert out["status"] == "failed"
    assert ("status_not_accepted" in out["error"]) or ("numeric_not_gt_zero" in out["error"])


@pytest.mark.asyncio
async def test_workflow_recipe_executor_rejects_etsy_without_screenshot_evidence():
    exe = WorkflowRecipeExecutor(_QueueEtsyDraftNoScreenshot())
    out = await exe.run_once("etsy_publish", {"dry_run": False}, trace_id="t5")
    assert out["status"] == "failed"
    assert "acceptance_gate_missing_required_evidence" in out["error"]


@pytest.mark.asyncio
async def test_workflow_recipe_executor_accepts_kdp_draft_with_evidence_and_fields():
    exe = WorkflowRecipeExecutor(_QueueKdpDraftWithEvidence())
    out = await exe.run_once("kdp_publish", {"dry_run": False}, trace_id="t6")
    assert out["status"] == "accepted"
    assert out["platform"] == "amazon_kdp"


@pytest.mark.asyncio
async def test_workflow_recipe_executor_rejects_etsy_without_file_proof_even_with_screenshot():
    exe = WorkflowRecipeExecutor(_QueueEtsyDraftWithScreenshotButNoFileProof())
    out = await exe.run_once(
        "etsy_publish",
        {"dry_run": False, "pdf_path": "/tmp/fake.pdf", "tags": ["a"], "materials": ["pdf"]},
        trace_id="t7",
    )
    assert out["status"] == "failed"
    assert "publish_quality_gate_failed" in out["error"]
