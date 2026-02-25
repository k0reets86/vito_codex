"""Тесты memory/memory_manager.py."""

import math
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from memory.memory_manager import MemoryManager


@pytest.fixture
def memory(tmp_path):
    """MemoryManager с временными путями."""
    with patch("memory.memory_manager.settings") as mock_settings:
        mock_settings.CHROMA_PATH = str(tmp_path / "chroma")
        mock_settings.SQLITE_PATH = str(tmp_path / "test.db")
        mock_settings.DATABASE_URL = "postgresql://test:test@localhost/test"
        mm = MemoryManager()
    # Переписываем paths напрямую чтобы работало при ленивом подключении
    mm._chroma_path = str(tmp_path / "chroma")
    mm._sqlite_path = str(tmp_path / "test.db")
    return mm


# ── SQLite ──

def test_sqlite_save_skill(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        memory.save_skill("test_skill", "A test skill")
    skill = memory.get_skill("test_skill")
    assert skill is not None
    assert skill["name"] == "test_skill"
    assert skill["description"] == "A test skill"
    assert skill["success_count"] == 0


def test_sqlite_save_skill_upsert(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        memory.save_skill("skill_x", "v1")
        memory.save_skill("skill_x", "v2")
    skill = memory.get_skill("skill_x")
    assert skill["description"] == "v2"
    assert skill["success_count"] == 1


def test_save_skill_self_improve_goes_pending_in_registry(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        memory.save_skill(
            "self_improve:test_case",
            "self improve draft",
            agent="vito_core",
            task_type="self_improve",
            method={"tests_passed": False},
        )
    from modules.skill_registry import SkillRegistry
    reg = SkillRegistry(sqlite_path=str(tmp_path / "test.db"))
    row = reg.get_skill("self_improve:test_case")
    assert row is not None
    assert row.get("acceptance_status") in {"pending", "accepted"}


def test_sqlite_get_skill_not_found(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        result = memory.get_skill("nonexistent")
    assert result is None


def test_sqlite_log_error(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        err_id = memory.log_error("test_module", "TestError", "something broke")
    assert err_id > 0


def test_sqlite_log_error_with_resolution(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        err_id = memory.log_error("mod", "Err", "broke", resolution="fixed it")
    assert err_id > 0


def test_sqlite_save_pattern(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        memory.save_pattern("pricing", "etsy_template", "4.99", confidence=0.8)
    conn = memory._get_sqlite()
    row = conn.execute(
        "SELECT * FROM patterns WHERE category='pricing' AND pattern_key='etsy_template'"
    ).fetchone()
    assert row is not None
    assert float(row["confidence"]) == 0.8


def test_sqlite_save_pattern_upsert(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        memory.save_pattern("cat", "key", "v1", 0.5)
        memory.save_pattern("cat", "key", "v2", 0.9)
    conn = memory._get_sqlite()
    row = conn.execute(
        "SELECT * FROM patterns WHERE category='cat' AND pattern_key='key'"
    ).fetchone()
    assert row["pattern_value"] == "v2"
    assert row["times_applied"] == 1


# ── ChromaDB ──

def test_chroma_store_and_search(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.CHROMA_PATH = str(tmp_path / "chroma")
        memory.store_knowledge("doc1", "Resume templates for Etsy", {"source": "test"})
        memory.store_knowledge("doc2", "Python programming tutorial", {"source": "test"})
        results = memory.search_knowledge("Etsy templates", n_results=2)

    assert len(results) > 0
    assert results[0]["id"] == "doc1"


def test_chroma_upsert(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.CHROMA_PATH = str(tmp_path / "chroma")
        memory.store_knowledge("doc1", "version 1")
        memory.store_knowledge("doc1", "version 2")
        results = memory.search_knowledge("version", n_results=1)

    assert results[0]["text"] == "version 2"


def test_chroma_search_empty(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.CHROMA_PATH = str(tmp_path / "chroma")
        results = memory.search_knowledge("anything")
    assert results == []


def test_store_knowledge_policy_forget_short_noise(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.CHROMA_PATH = str(tmp_path / "chroma")
        s.SQLITE_PATH = str(tmp_path / "test.db")
        stored = memory.store_knowledge("noise_1", "ok", {"type": "debug", "source": "heartbeat"})
    assert stored is False
    audit = memory.get_memory_policy_audit(limit=1)
    assert audit
    assert audit[0]["doc_id"] == "noise_1"
    assert audit[0]["action"] == "forget"


def test_store_knowledge_policy_force_save(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.CHROMA_PATH = str(tmp_path / "chroma")
        s.SQLITE_PATH = str(tmp_path / "test.db")
        stored = memory.store_knowledge(
            "owner_pref_tone",
            "owner preference: concise",
            {"type": "owner_preference", "force_save": True},
        )
    assert stored is True
    results = memory.search_knowledge("concise", n_results=1)
    assert results
    assert results[0]["id"] == "owner_pref_tone"


def test_forget_knowledge_records_audit(memory, tmp_path):
    with patch("memory.memory_manager.settings") as s:
        s.CHROMA_PATH = str(tmp_path / "chroma")
        s.SQLITE_PATH = str(tmp_path / "test.db")
        memory.store_knowledge("doc_forget", "This is important content for test", {"type": "lesson"})
        deleted = memory.forget_knowledge("doc_forget", reason="test_cleanup")
    assert deleted is True
    audit = memory.get_memory_policy_audit(limit=5)
    assert any(r["doc_id"] == "doc_forget" and r["action"] == "forget" for r in audit)


# ── Формула релевантности ──

def test_relevance_recent_important():
    now = datetime.now(timezone.utc)
    score = MemoryManager.calculate_relevance(0.9, now, importance=0.8)
    assert 0.8 < score <= 1.0


def test_relevance_old_unimportant():
    old = datetime.now(timezone.utc) - timedelta(days=90)
    score = MemoryManager.calculate_relevance(0.3, old, importance=0.2)
    assert score < 0.3


def test_relevance_formula_weights():
    now = datetime.now(timezone.utc)
    # recency = exp(0/30) = 1.0 для свежего документа
    score = MemoryManager.calculate_relevance(1.0, now, importance=1.0)
    expected = 0.60 * 1.0 + 0.25 * 1.0 + 0.15 * 1.0  # 1.0
    assert abs(score - expected) < 0.01


def test_relevance_decay():
    now = datetime.now(timezone.utc)
    score_fresh = MemoryManager.calculate_relevance(0.5, now, 0.5)
    score_old = MemoryManager.calculate_relevance(
        0.5, now - timedelta(days=60), 0.5
    )
    assert score_fresh > score_old


# ── PostgreSQL (моки) ──

@pytest.mark.asyncio
async def test_store_episode(memory, mock_pg_pool):
    memory._pg_pool = mock_pg_pool
    episode_id = await memory.store_episode(
        event_type="test", summary="Test episode", details={"key": "val"}, importance=0.8
    )
    assert episode_id == 1
    mock_pg_pool.acquire.assert_called_once()


@pytest.mark.asyncio
async def test_store_to_datalake(memory, mock_pg_pool):
    memory._pg_pool = mock_pg_pool
    dl_id = await memory.store_to_datalake(
        action_type="test_action",
        agent="test_agent",
        input_data={"in": 1},
        output_data={"out": 2},
        result="ok",
        duration_ms=100,
        cost_usd=0.01,
    )
    assert dl_id == 1


@pytest.mark.asyncio
async def test_search_episodes(memory, mock_pg_pool):
    memory._pg_pool = mock_pg_pool
    results = await memory.search_episodes("test")
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_close(memory, tmp_path, mock_pg_pool):
    with patch("memory.memory_manager.settings") as s:
        s.SQLITE_PATH = str(tmp_path / "test.db")
        memory.save_skill("x", "y")  # инициализирует SQLite

    assert memory._sqlite_conn is not None
    memory._pg_pool = mock_pg_pool
    await memory.close()
    # close() закрывает соединения; pg_pool.close() вызван
    mock_pg_pool.close.assert_called_once()
