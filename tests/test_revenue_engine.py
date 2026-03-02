import asyncio
from unittest.mock import AsyncMock

import pytest

from config.settings import settings
from agents.base_agent import TaskResult
from modules.revenue_engine import RevenueEngine


class _Registry:
    def __init__(self):
        self.dispatch = AsyncMock(side_effect=self._dispatch)

    async def _dispatch(self, capability, **kwargs):
        if capability == "niche_research":
            return TaskResult(success=True, output="AI Prompt Pack for Freelancers")
        if capability == "product_description":
            return TaskResult(success=True, output="A compact bundle of prompts and templates for solo freelancers.")
        if capability == "quality_review":
            return TaskResult(success=True, output={"score": 8.2, "approved": True})
        if capability == "sales_check":
            return TaskResult(success=True, output={"gumroad": {"sales": 0, "revenue": 0}})
        return TaskResult(success=False, error=f"unknown_capability:{capability}")


class _Queue:
    def __init__(self, evidence: str = ""):
        self._jobs = []
        self._id = 0
        self._evidence = evidence

    def enqueue(self, platform, payload, max_attempts=1, trace_id=""):
        self._id += 1
        self._jobs.append(
            {
                "id": self._id,
                "platform": platform,
                "payload": payload,
                "status": "queued",
                "evidence": self._evidence,
                "trace_id": trace_id,
                "max_attempts": max_attempts,
            }
        )
        return self._id

    async def process_all(self, limit=20):
        out = []
        count = 0
        for j in self._jobs:
            if j["status"] == "queued":
                j["status"] = "done"
                out.append({"job_id": j["id"], "status": "done"})
                count += 1
                if count >= limit:
                    break
        return out

    def list_jobs(self, limit=200):
        return list(reversed(self._jobs))[:limit]

    def stats(self):
        done = sum(1 for j in self._jobs if j["status"] == "done")
        queued = sum(1 for j in self._jobs if j["status"] == "queued")
        return {"queued": queued, "running": 0, "done": done, "failed": 0, "total": len(self._jobs)}


class _QueueMissingPlatform(_Queue):
    def __init__(self):
        super().__init__(evidence="")
        self.platforms = {}


class _QueueNoStats(_Queue):
    stats = None


class _QueueStatsError(_Queue):
    def stats(self):
        raise RuntimeError("stats backend failed")


class _QueueInvalidStats(_Queue):
    def stats(self):
        return {"queued": -1, "running": 0, "done": 0, "failed": 0, "total": 0}


class _QueueMalformedStats(_Queue):
    def stats(self):
        return {"queued": "oops", "running": "nan", "done": "bad", "failed": 1, "total": 2}


class _QueueMalformedRunningStats(_Queue):
    def stats(self):
        return {"queued": 0, "running": "oops", "done": 0, "failed": 0, "total": 1}


class _QueueMalformedDoneStats(_Queue):
    def stats(self):
        return {"queued": 0, "running": 0, "done": "oops", "failed": 0, "total": 1}


class _QueueMalformedFailedStats(_Queue):
    def stats(self):
        return {"queued": 0, "running": 0, "done": 0, "failed": "oops", "total": 1}


class _QueueMalformedTotalStats(_Queue):
    def stats(self):
        return {"queued": 0, "running": 0, "done": 0, "failed": 0, "total": "oops"}


class _QueueMalformedRunningAgeStats(_Queue):
    def stats(self):
        return {
            "queued": 1,
            "running": 1,
            "done": 0,
            "failed": 0,
            "total": 2,
            "oldest_running_sec": "oops",
        }


class _QueueMalformedQueuedAgeStats(_Queue):
    def stats(self):
        return {
            "queued": 1,
            "running": 0,
            "done": 0,
            "failed": 0,
            "total": 1,
            "oldest_queued_sec": "oops",
        }


class _QueueNonDictStats(_Queue):
    def stats(self):
        return ["queued", 1]


class _QueueNonDictStringStats(_Queue):
    def stats(self):
        return "queued=1"


class _QueueNoneStats(_Queue):
    def stats(self):
        return None


class _QueueMissingRequiredStats(_Queue):
    def stats(self):
        return {"failed": 0, "queued": 1, "running": 0}


class _QueueInconsistentStats(_Queue):
    def stats(self):
        return {"queued": 2, "running": 2, "done": 0, "failed": 2, "total": 3}


class _QueueInconsistentDoneStats(_Queue):
    def stats(self):
        return {"queued": 0, "running": 0, "done": 5, "failed": 0, "total": 3}


class _QueueZeroTotalWithActivity(_Queue):
    def stats(self):
        return {"queued": 0, "running": 0, "done": 0, "failed": 1, "total": 0}


class _QueueOrphanAgeStats(_Queue):
    def stats(self):
        return {
            "queued": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
            "total": 0,
            "oldest_queued_sec": 120,
            "oldest_running_sec": 90,
        }


class _QueueOrphanRunningAgeStats(_Queue):
    def stats(self):
        return {
            "queued": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
            "total": 0,
            "oldest_running_sec": 120,
        }


class _QueueTotalWithZeroCounters(_Queue):
    def stats(self):
        return {"queued": 0, "running": 0, "done": 0, "failed": 0, "total": 5}


class _AuthAdapter:
    def __init__(self, ok=True, delay_sec=0.0, raise_error=False):
        self.ok = ok
        self.delay_sec = float(delay_sec)
        self.raise_error = bool(raise_error)

    async def authenticate(self):
        if self.delay_sec > 0:
            await asyncio.sleep(self.delay_sec)
        if self.raise_error:
            raise RuntimeError("boom")
        return bool(self.ok)


class _AuthAdapterWithBrowser(_AuthAdapter):
    def __init__(self, ok=True, delay_sec=0.0, raise_error=False):
        super().__init__(ok=ok, delay_sec=delay_sec, raise_error=raise_error)
        self.browser_agent = object()


class _QueueWithAdapter(_Queue):
    def __init__(self, adapter, evidence: str = ""):
        super().__init__(evidence=evidence)
        self.platforms = {"gumroad": adapter}


class _SlowQueue(_Queue):
    async def process_all(self, limit=20):
        await asyncio.sleep(2.0)
        return await super().process_all(limit=limit)


class _QueueBacklog(_Queue):
    def __init__(self, failed=0, queued=0, evidence: str = ""):
        super().__init__(evidence=evidence)
        self._failed = int(failed)
        self._queued = int(queued)

    def stats(self):
        done = sum(1 for j in self._jobs if j["status"] == "done")
        total = len(self._jobs) + self._failed
        return {"queued": self._queued, "running": 0, "done": done, "failed": self._failed, "total": total}


class _QueueBacklogAge(_QueueBacklog):
    def __init__(self, failed=0, queued=0, oldest_queued_sec=0, evidence: str = ""):
        super().__init__(failed=failed, queued=queued, evidence=evidence)
        self._oldest_queued_sec = int(oldest_queued_sec)

    def stats(self):
        out = super().stats()
        out["oldest_queued_sec"] = self._oldest_queued_sec
        return out


class _QueueBacklogRunning(_QueueBacklog):
    def __init__(self, failed=0, queued=0, running=0, evidence: str = ""):
        super().__init__(failed=failed, queued=queued, evidence=evidence)
        self._running = int(running)

    def stats(self):
        out = super().stats()
        out["running"] = self._running
        return out


class _QueueBacklogRunningAge(_QueueBacklogRunning):
    def __init__(self, failed=0, queued=0, running=0, oldest_running_sec=0, evidence: str = ""):
        super().__init__(failed=failed, queued=queued, running=running, evidence=evidence)
        self._oldest_running_sec = int(oldest_running_sec)

    def stats(self):
        out = super().stats()
        out["oldest_running_sec"] = self._oldest_running_sec
        return out


class _Comms:
    def __init__(self, approved=True):
        self.approved = approved
        self.requests = []

    async def request_approval(self, request_id, message, timeout_seconds=3600):
        self.requests.append((request_id, message, timeout_seconds))
        return True if self.approved else False


@pytest.mark.asyncio
async def test_revenue_engine_cycle_completed(tmp_path):
    db = str(tmp_path / "rev.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=_Comms(approved=True),
        publisher_queue=_Queue(),
        dry_run=True,
        require_approval=True,
    )
    assert out["ok"] is True
    assert out["status"] == "completed"
    data = engine.get_cycle(int(out["cycle_id"]))
    assert data["cycle"]["status"] == "completed"
    assert len(data["steps"]) >= 5


@pytest.mark.asyncio
async def test_revenue_engine_cycle_rejected_on_approval(tmp_path):
    db = str(tmp_path / "rev_reject.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=_Comms(approved=False),
        publisher_queue=_Queue(),
        dry_run=True,
        require_approval=True,
    )
    assert out["ok"] is False
    assert "approval_rejected" in out["error"]
    data = engine.get_cycle(int(out["cycle_id"]))
    assert data["cycle"]["status"] == "failed"


@pytest.mark.asyncio
async def test_revenue_engine_build_and_persist_cycle_report(tmp_path):
    db = str(tmp_path / "rev_report.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=_Comms(approved=True),
        publisher_queue=_Queue(),
        dry_run=True,
        require_approval=True,
    )
    assert out["ok"] is True
    cycle_id = int(out["cycle_id"])

    report = engine.build_cycle_report(cycle_id)
    assert report["cycle_id"] == cycle_id
    assert report["status"] == "completed"
    assert report["steps_total"] >= 5
    assert isinstance(report["analysis"], dict)

    md = engine.render_cycle_report_markdown(cycle_id)
    assert f"Revenue Cycle Report #{cycle_id}" in md
    assert "## Steps" in md

    save = engine.persist_cycle_report(cycle_id, out_path=str(tmp_path / "revenue_report.md"))
    assert save["ok"] is True
    assert save["cycle_id"] == cycle_id
    assert (tmp_path / "revenue_report.md").exists()


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_requires_publish_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    db = str(tmp_path / "rev_live_guard.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_Queue(evidence=""),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert out["error"] == "publish_missing_evidence"
    data = engine.get_cycle(int(out["cycle_id"]))
    assert data["cycle"]["status"] == "failed"


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_precheck_without_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "")
    monkeypatch.setattr(settings, "GUMROAD_OAUTH_TOKEN", "")
    monkeypatch.setattr(settings, "GUMROAD_EMAIL", "")
    monkeypatch.setattr(settings, "GUMROAD_PASSWORD", "")
    db = str(tmp_path / "rev_live_precheck.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_Queue(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "gumroad_auth_missing" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_on_invalid_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    db = str(tmp_path / "rev_live_invalid_evidence.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_Queue(evidence="job:123"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert out["error"] == "publish_invalid_evidence"


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_on_queue_backlog(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", 0)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_QUEUED", 1)
    db = str(tmp_path / "rev_live_backlog.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueBacklog(failed=2, queued=3, evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_failed_backlog" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_on_queue_fail_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", 10)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAIL_RATE", 0.3)
    db = str(tmp_path / "rev_live_fail_rate.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueBacklog(failed=3, queued=0, evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_fail_rate" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_ignores_fail_rate_below_min_total(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", 10)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAIL_RATE", 0.25)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_FAIL_RATE_MIN_TOTAL", 5)
    db = str(tmp_path / "rev_live_fail_rate_min_total.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueBacklog(failed=2, queued=0, evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is True
    assert out["status"] == "completed"


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_required.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueNoStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_unavailable" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_raise_error(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_error.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueStatsError(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_unavailable" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_non_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_non_dict.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueNonDictStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:stats_non_dict" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_non_dict_string(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_non_dict_string.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueNonDictStringStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:stats_non_dict" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_none(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_none.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueNoneStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_unavailable" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_malformed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_malformed.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMalformedStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:queued_parse" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_running_parse_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_running_parse.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMalformedRunningStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:running_parse" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_done_parse_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_done_parse.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMalformedDoneStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:done_parse" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_failed_parse_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_failed_parse.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMalformedFailedStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:failed_parse" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_total_parse_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_total_parse.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMalformedTotalStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:total_parse" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_running_age_parse_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_running_age_parse.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMalformedRunningAgeStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:oldest_running_sec_parse" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_queued_age_parse_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_queued_age_parse.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMalformedQueuedAgeStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:oldest_queued_sec_parse" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_missing_required_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_missing_required.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMissingRequiredStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:missing_required_keys" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_stats_negative_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_negative_invalid.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueInvalidStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:queued" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_total_with_zero_counters(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_total_zero_counters.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueTotalWithZeroCounters(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:total_with_zero_counters" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_total_zero_with_activity(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_total_zero_with_activity.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueZeroTotalWithActivity(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:total_zero_with_activity" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_age_without_backlog(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_age_without_backlog.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueOrphanAgeStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:queued_age_without_queue" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_running_age_without_backlog(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_running_age_without_backlog.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueOrphanRunningAgeStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:running_age_without_running" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_total_lt_accounted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_total_lt_accounted.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueInconsistentDoneStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:total_lt_accounted" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_queue_total_lt_active(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    db = str(tmp_path / "rev_live_stats_total_lt_active.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueInconsistentStats(evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_stats_invalid:total_lt_active" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_summary_counts_cycles(tmp_path):
    db = str(tmp_path / "rev_summary.db")
    engine = RevenueEngine(sqlite_path=db)
    ok_cycle = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=_Comms(approved=True),
        publisher_queue=_Queue(evidence="https://gumroad.example/p/123"),
        dry_run=True,
        require_approval=True,
    )
    assert ok_cycle["ok"] is True
    bad_cycle = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=_Comms(approved=False),
        publisher_queue=_Queue(evidence="https://gumroad.example/p/456"),
        dry_run=True,
        require_approval=True,
    )
    assert bad_cycle["ok"] is False
    summary = engine.summarize_cycles(days=30)
    assert summary["total_cycles"] >= 2
    assert summary["completed_cycles"] >= 1
    assert summary["failed_cycles"] >= 1
    assert summary["completion_rate"] <= 1.0


@pytest.mark.asyncio
async def test_revenue_engine_analysis_contains_iterate_actions(tmp_path):
    db = str(tmp_path / "rev_iterate.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=_Comms(approved=True),
        publisher_queue=_Queue(evidence="https://gumroad.example/p/iter"),
        dry_run=True,
        require_approval=True,
    )
    assert out["ok"] is True
    analysis = out.get("analysis", {}) or {}
    actions = analysis.get("iterate_actions", []) or []
    assert isinstance(actions, list)
    assert len(actions) >= 1
    assert any("marketing" in a.lower() or "evidence" in a.lower() or "publish" in a.lower() for a in actions)


@pytest.mark.asyncio
async def test_revenue_engine_fails_fast_when_queue_missing_gumroad_adapter(tmp_path):
    db = str(tmp_path / "rev_missing_adapter.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueMissingPlatform(),
        dry_run=True,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "publisher_queue_missing_gumroad_adapter" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_auto_report_persisted_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_AUTO_REPORT_ENABLED", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_REPORT_DIR", str(tmp_path / "reports"))
    db = str(tmp_path / "rev_auto_report.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=_Comms(approved=True),
        publisher_queue=_Queue(evidence="https://gumroad.example/p/auto"),
        dry_run=True,
        require_approval=True,
    )
    assert out["ok"] is True
    report_path = str(out.get("report_path", "") or "")
    assert report_path.endswith(".md")
    assert (tmp_path / "reports" / f"revenue_cycle_{int(out['cycle_id'])}_latest.md").exists()


@pytest.mark.asyncio
async def test_revenue_engine_publish_fails_on_queue_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_PUBLISH_TIMEOUT_SEC", 1)
    db = str(tmp_path / "rev_publish_timeout.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_SlowQueue(evidence="https://gumroad.example/p/slow"),
        dry_run=True,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publisher_queue_timeout:")


def test_revenue_engine_publish_precheck_combines_issues(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "")
    monkeypatch.setattr(settings, "GUMROAD_OAUTH_TOKEN", "")
    monkeypatch.setattr(settings, "GUMROAD_EMAIL", "")
    monkeypatch.setattr(settings, "GUMROAD_PASSWORD", "")

    class _QueueNoAdapter:
        platforms = {}

    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=_QueueNoAdapter())
    assert ok is False
    assert "publisher_queue_missing_gumroad_adapter" in issues
    assert "gumroad_auth_missing" in issues


def test_revenue_engine_publish_precheck_fails_on_backlog(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", 0)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_QUEUED", 2)
    q = _QueueBacklog(failed=3, queued=5)
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any(str(i).startswith("publisher_queue_failed_backlog:") for i in issues)
    assert any(str(i).startswith("publisher_queue_queued_backlog:") for i in issues)


def test_revenue_engine_publish_precheck_fails_on_stale_queued_age(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", 10)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_QUEUED", 10)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUED_AGE_SEC", 300)
    q = _QueueBacklogAge(failed=0, queued=2, oldest_queued_sec=900)
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any(str(i).startswith("publisher_queue_queued_age:") for i in issues)


def test_revenue_engine_publish_precheck_fails_on_running_backlog(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", 10)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_QUEUED", 10)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_RUNNING", 1)
    q = _QueueBacklogRunning(failed=0, queued=0, running=3)
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any(str(i).startswith("publisher_queue_running_backlog:") for i in issues)


def test_revenue_engine_publish_precheck_fails_on_total_backlog(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_TOTAL", 2)
    q = _QueueBacklog(failed=3, queued=0)
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any(str(i).startswith("publisher_queue_total_backlog:") for i in issues)


def test_revenue_engine_publish_precheck_fails_on_queue_fail_rate(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAIL_RATE", 0.25)
    q = _QueueBacklog(failed=2, queued=0)
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any(str(i).startswith("publisher_queue_fail_rate:") for i in issues)


def test_revenue_engine_publish_precheck_ignores_fail_rate_below_min_total(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAIL_RATE", 0.25)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_FAIL_RATE_MIN_TOTAL", 5)
    q = _QueueBacklog(failed=2, queued=0)
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert all(not str(i).startswith("publisher_queue_fail_rate:") for i in issues)


def test_revenue_engine_publish_precheck_fails_when_stats_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueNoStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert "publisher_queue_stats_unavailable" in issues


def test_revenue_engine_publish_precheck_fails_when_stats_invalid(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueInvalidStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any(str(i).startswith("publisher_queue_stats_invalid:") for i in issues)


def test_revenue_engine_publish_precheck_fails_when_stats_malformed(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueMalformedStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any("publisher_queue_stats_invalid:queued_parse" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_when_stats_non_dict(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueNonDictStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert "publisher_queue_stats_unavailable" in issues
    assert any("publisher_queue_stats_invalid:stats_non_dict" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_when_stats_missing_required_keys(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueMissingRequiredStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any("publisher_queue_stats_invalid:missing_required_keys" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_when_stats_inconsistent(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueInconsistentStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any("publisher_queue_stats_invalid:total_lt_active" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_when_total_lt_accounted(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueInconsistentDoneStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any("publisher_queue_stats_invalid:total_lt_accounted" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_when_total_zero_with_activity(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueZeroTotalWithActivity()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any("publisher_queue_stats_invalid:total_zero_with_activity" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_when_age_without_backlog(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueOrphanAgeStats()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any("publisher_queue_stats_invalid:queued_age_without_queue" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_when_total_with_zero_counters(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)
    q = _QueueTotalWithZeroCounters()
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any("publisher_queue_stats_invalid:total_with_zero_counters" in str(i) for i in issues)


def test_revenue_engine_publish_precheck_fails_on_stale_running_age(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_MAX_RUNNING_AGE_SEC", 120)
    q = _QueueBacklogRunningAge(failed=0, queued=0, running=1, oldest_running_sec=900)
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert any(str(i).startswith("publisher_queue_running_age:") for i in issues)


def test_revenue_engine_publish_precheck_fails_when_browser_runtime_required(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", False)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_BROWSER_RUNTIME", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_SESSION_COOKIE", False)
    q = _QueueWithAdapter(adapter=_AuthAdapter(ok=True))
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert "gumroad_browser_runtime_unavailable" in issues


def test_revenue_engine_publish_precheck_fails_when_cookie_required_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", False)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_BROWSER_RUNTIME", False)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_SESSION_COOKIE", True)
    monkeypatch.setattr(settings, "GUMROAD_SESSION_COOKIE_FILE", str(tmp_path / "missing_cookie.txt"))
    q = _QueueWithAdapter(adapter=_AuthAdapterWithBrowser(ok=True))
    ok, issues = RevenueEngine._publish_precheck(dry_run=False, publisher_queue=q)
    assert ok is False
    assert "gumroad_session_cookie_missing" in issues


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_fails_when_browser_runtime_required_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", False)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_BROWSER_RUNTIME", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_SESSION_COOKIE", False)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_CHECK_ADAPTER_AUTH", True)
    db = str(tmp_path / "rev_live_browser_required.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueWithAdapter(adapter=_AuthAdapter(ok=True), evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is False
    assert str(out["error"]).startswith("publish_precheck_failed:")
    assert "gumroad_browser_runtime_unavailable" in str(out["error"])


@pytest.mark.asyncio
async def test_revenue_engine_live_cycle_passes_browser_runtime_when_cookie_present(tmp_path, monkeypatch):
    cookie = tmp_path / "gumroad_cookie.txt"
    cookie.write_text("session_token", encoding="utf-8")
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", False)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_BROWSER_RUNTIME", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_SESSION_COOKIE", True)
    monkeypatch.setattr(settings, "GUMROAD_SESSION_COOKIE_FILE", str(cookie))
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_CHECK_ADAPTER_AUTH", True)
    db = str(tmp_path / "rev_live_browser_ok.db")
    engine = RevenueEngine(sqlite_path=db)
    out = await engine.run_gumroad_cycle(
        registry=_Registry(),
        llm_router=None,
        comms=None,
        publisher_queue=_QueueWithAdapter(adapter=_AuthAdapterWithBrowser(ok=True), evidence="https://gumroad.example/p/ok"),
        dry_run=False,
        require_approval=False,
    )
    assert out["ok"] is True
    assert out["status"] == "completed"


@pytest.mark.asyncio
async def test_revenue_engine_publish_precheck_async_checks_adapter_auth(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_CHECK_ADAPTER_AUTH", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_AUTH_TIMEOUT_SEC", 1)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    q = _QueueWithAdapter(adapter=_AuthAdapter(ok=False))
    ok, issues = await RevenueEngine._publish_precheck_async(dry_run=False, publisher_queue=q)
    assert ok is False
    assert "gumroad_adapter_auth_failed" in issues


@pytest.mark.asyncio
async def test_revenue_engine_publish_precheck_async_adapter_auth_timeout(monkeypatch):
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_CHECK_ADAPTER_AUTH", True)
    monkeypatch.setattr(settings, "REVENUE_ENGINE_LIVE_AUTH_TIMEOUT_SEC", 1)
    monkeypatch.setattr(settings, "GUMROAD_API_KEY", "test_key")
    q = _QueueWithAdapter(adapter=_AuthAdapter(ok=True, delay_sec=2.0))
    ok, issues = await RevenueEngine._publish_precheck_async(dry_run=False, publisher_queue=q)
    assert ok is False
    assert "gumroad_adapter_auth_timeout" in issues
