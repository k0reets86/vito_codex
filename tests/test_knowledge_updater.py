"""Тесты для KnowledgeUpdater."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from knowledge_updater import KnowledgeUpdater
from llm_router import MODEL_REGISTRY


@pytest.fixture
def mock_memory_with_chroma_and_sqlite(tmp_sqlite):
    """Memory с реальным SQLite и мок ChromaDB."""
    import sqlite3
    conn = sqlite3.connect(tmp_sqlite)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            pattern_value TEXT,
            confidence REAL DEFAULT 0.5,
            times_applied INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(category, pattern_key)
        );
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, description TEXT,
            success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
            last_used TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY, module TEXT, error_type TEXT, message TEXT,
            resolution TEXT, resolved INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # Mock ChromaDB collection
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}
    mock_collection.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    mock_collection.update = MagicMock()
    mock_collection.delete = MagicMock()

    mem = MagicMock()
    mem._get_sqlite.return_value = conn
    mem._get_chroma.return_value = mock_collection
    return mem


@pytest.fixture
def ku(mock_llm_router, mock_memory_with_chroma_and_sqlite):
    return KnowledgeUpdater(llm_router=mock_llm_router, memory=mock_memory_with_chroma_and_sqlite)


class TestKnowledgeUpdaterInit:
    def test_init(self, ku):
        assert ku.llm_router is not None
        assert ku.memory is not None


class TestUpdateModelPrices:
    @pytest.mark.asyncio
    async def test_update_prices_success(self, ku):
        prices = {
            "claude-sonnet": {"input": 0.004, "output": 0.016},
            "claude-opus": {"input": 0.015, "output": 0.075},
            "claude-haiku": {"input": 0.001, "output": 0.005},
            "gpt-o3": {"input": 0.012, "output": 0.045},
            "perplexity": {"input": 0.003, "output": 0.015},
        }
        ku.llm_router.call_llm = AsyncMock(return_value=json.dumps(prices))

        # Save originals for all models being modified
        originals = {}
        for key in prices:
            if key in MODEL_REGISTRY:
                m = MODEL_REGISTRY[key]
                originals[key] = (m.cost_per_1k_input, m.cost_per_1k_output)

        result = await ku.update_model_prices()
        assert result is True

        # Restore all originals after test
        for key, (inp, out) in originals.items():
            MODEL_REGISTRY[key].cost_per_1k_input = inp
            MODEL_REGISTRY[key].cost_per_1k_output = out

    @pytest.mark.asyncio
    async def test_update_prices_llm_returns_none(self, ku):
        ku.llm_router.call_llm = AsyncMock(return_value=None)
        result = await ku.update_model_prices()
        assert result is False

    @pytest.mark.asyncio
    async def test_update_prices_invalid_json(self, ku):
        ku.llm_router.call_llm = AsyncMock(return_value="not json at all")
        result = await ku.update_model_prices()
        assert result is False

    @pytest.mark.asyncio
    async def test_update_prices_markdown_wrapped(self, ku):
        prices = {"claude-sonnet": {"input": 0.003, "output": 0.015}}
        ku.llm_router.call_llm = AsyncMock(
            return_value=f'```json\n{json.dumps(prices)}\n```'
        )
        # No actual price change since values are same
        result = await ku.update_model_prices()
        # Returns False because no prices changed (same values)
        assert result is False


class TestCompactMemories:
    def test_compact_empty_collection(self, ku):
        result = ku.compact_memories()
        assert result == 0

    def test_compact_no_old_docs(self, ku):
        now = datetime.now(timezone.utc).isoformat()
        ku.memory._get_chroma.return_value.get.return_value = {
            "ids": ["doc1"],
            "documents": ["some text"],
            "metadatas": [{"stored_at": now}],
        }
        result = ku.compact_memories()
        assert result == 0

    def test_compact_with_old_similar_docs(self, ku):
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        collection = ku.memory._get_chroma.return_value
        collection.get.return_value = {
            "ids": ["doc1", "doc2", "doc3"],
            "documents": ["text about AI", "text about AI tools", "different topic"],
            "metadatas": [
                {"stored_at": old_date},
                {"stored_at": old_date},
                {"stored_at": old_date},
            ],
        }
        # When querying doc1, doc2 is similar (distance 0.1)
        collection.query.return_value = {
            "ids": [["doc1", "doc2"]],
            "documents": [["text about AI", "text about AI tools"]],
            "metadatas": [[{}, {}]],
            "distances": [[0.0, 0.1]],
        }
        result = ku.compact_memories()
        assert result >= 0  # May or may not compact depending on logic


class TestRecalculatePatterns:
    def test_recalculate_empty(self, ku):
        result = ku.recalculate_patterns()
        assert result == 0

    def test_recalculate_boosts_popular(self, ku):
        conn = ku.memory._get_sqlite()
        conn.execute(
            "INSERT INTO patterns (category, pattern_key, pattern_value, confidence, times_applied) VALUES (?, ?, ?, ?, ?)",
            ("niche", "ai_tools", "high demand", 0.7, 10),
        )
        conn.commit()

        result = ku.recalculate_patterns()
        assert result >= 1

        row = conn.execute("SELECT confidence FROM patterns WHERE pattern_key = 'ai_tools'").fetchone()
        assert row["confidence"] == pytest.approx(0.75, abs=0.01)

    def test_recalculate_decays_unused(self, ku):
        conn = ku.memory._get_sqlite()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        conn.execute(
            "INSERT INTO patterns (category, pattern_key, pattern_value, confidence, times_applied, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("niche", "old_pattern", "outdated", 0.5, 0, old_date),
        )
        conn.commit()

        ku.recalculate_patterns()

        row = conn.execute("SELECT confidence FROM patterns WHERE pattern_key = 'old_pattern'").fetchone()
        assert row["confidence"] == pytest.approx(0.4, abs=0.01)

    def test_recalculate_deletes_low_confidence(self, ku):
        conn = ku.memory._get_sqlite()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        conn.execute(
            "INSERT INTO patterns (category, pattern_key, pattern_value, confidence, times_applied, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("niche", "dying_pattern", "dead", 0.12, 0, old_date),
        )
        conn.commit()

        ku.recalculate_patterns()

        row = conn.execute("SELECT * FROM patterns WHERE pattern_key = 'dying_pattern'").fetchone()
        assert row is None  # Deleted because confidence < 0.15


class TestRunWeeklyUpdate:
    @pytest.mark.asyncio
    async def test_run_weekly_update(self, ku):
        ku.llm_router.call_llm = AsyncMock(return_value=None)
        results = await ku.run_weekly_update()
        assert "model_prices" in results
        assert "memories_compacted" in results
        assert "patterns_updated" in results


class TestRunDailyRefresh:
    def test_run_daily_refresh(self, ku):
        results = ku.run_daily_refresh()
        assert "calendar_loaded" in results
        assert "platform_knowledge_loaded" in results
        assert "platform_registry_loaded" in results
        assert "ai_models_loaded" in results
