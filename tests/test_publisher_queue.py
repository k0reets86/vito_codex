import asyncio

import pytest

from modules.publisher_queue import PublisherQueue


class _OkPlatform:
    async def publish(self, payload: dict) -> dict:
        return {
            "platform": "x",
            "status": "prepared",
            "url": "https://example.com/ok",
            "payload": payload,
        }


class _FailPlatform:
    async def publish(self, payload: dict) -> dict:
        return {"platform": "x", "status": "error", "error": "boom"}


class _NoEvidencePlatform:
    async def publish(self, payload: dict) -> dict:
        return {"platform": "x", "status": "published"}


class _EtsyWeakDraftPlatform:
    async def publish(self, payload: dict) -> dict:
        return {
            "platform": "etsy",
            "status": "draft",
            "listing_id": "123",
            "url": "https://www.etsy.com/listing/123",
            "screenshot_path": "runtime/etsy.png",
            "editor_audit": {"hasUploadPrompt": True, "image_count": 2, "hasTags": True, "hasMaterials": True},
        }


class _SlowPlatform:
    async def publish(self, payload: dict) -> dict:
        await asyncio.sleep(0.05)
        return {"platform": "x", "status": "prepared", "url": "https://example.com/late"}


@pytest.mark.asyncio
async def test_publisher_queue_success(tmp_path):
    db = str(tmp_path / "pq.db")
    pq = PublisherQueue(platforms={"twitter": _OkPlatform()}, sqlite_path=db)
    jid = pq.enqueue("twitter", {"dry_run": True, "text": "hello"})
    assert jid > 0
    out = await pq.process_once()
    assert out
    assert out["status"] == "done"
    st = pq.stats()
    assert st["done"] >= 1


@pytest.mark.asyncio
async def test_publisher_queue_retry_then_fail(tmp_path):
    db = str(tmp_path / "pq2.db")
    pq = PublisherQueue(platforms={"twitter": _FailPlatform()}, sqlite_path=db)
    pq.enqueue("twitter", {"x": 1}, max_attempts=2)
    r1 = await pq.process_once()
    assert r1 and r1["status"] in {"queued", "failed"}
    r2 = await pq.process_once()
    assert r2 and r2["status"] == "failed"
    st = pq.stats()
    assert st["failed"] >= 1


@pytest.mark.asyncio
async def test_publisher_queue_missing_evidence_fails(tmp_path):
    db = str(tmp_path / "pq3.db")
    pq = PublisherQueue(platforms={"twitter": _NoEvidencePlatform()}, sqlite_path=db)
    pq.enqueue("twitter", {"text": "hello"}, max_attempts=1)
    r = await pq.process_once()
    assert r and r["status"] == "failed"


@pytest.mark.asyncio
async def test_publisher_queue_times_out_stuck_publish(tmp_path):
    db = str(tmp_path / "pq4.db")
    pq = PublisherQueue(platforms={"twitter": _SlowPlatform()}, sqlite_path=db)
    pq.publish_timeout_seconds = 0.01
    pq.enqueue("twitter", {"text": "hello"}, max_attempts=1)
    r = await pq.process_once()
    assert r and r["status"] == "failed"
    assert "publish_timeout" in r["error"]


@pytest.mark.asyncio
async def test_publisher_queue_rejects_platform_quality_gap(tmp_path):
    db = str(tmp_path / "pq5.db")
    pq = PublisherQueue(platforms={"etsy": _EtsyWeakDraftPlatform()}, sqlite_path=db)
    pq.enqueue("etsy", {"pdf_path": "/tmp/fake.pdf", "tags": ["a"], "materials": ["pdf guide"]}, max_attempts=1)
    r = await pq.process_once()
    assert r and r["status"] == "failed"
    assert "publish_quality_gate_failed" in r["error"]
