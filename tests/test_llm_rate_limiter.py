import asyncio

import pytest

from modules.llm_rate_limiter import LLMRateLimiter, RateLimitDecision
from modules import llm_rate_limiter as llm_rate_limiter_module


def test_llm_rate_limiter_peek_and_mark(tmp_path, monkeypatch):
    db = tmp_path / "rl.db"
    monkeypatch.setattr(llm_rate_limiter_module.settings, "LLM_RATE_LIMIT_OPENAI_RPM", 2, raising=False)
    limiter = LLMRateLimiter(sqlite_path=str(db))
    assert limiter.peek("openai").allowed is True
    limiter.mark("openai", "gpt-4o", "routine")
    limiter.mark("openai", "gpt-4o", "routine")
    decision = limiter.peek("openai")
    assert decision.allowed is False
    assert decision.wait_seconds >= 0


def test_llm_rate_limiter_stats(tmp_path):
    db = tmp_path / "rl2.db"
    limiter = LLMRateLimiter(sqlite_path=str(db))
    limiter.mark("google", "gemini", "research")
    stats = limiter.stats()
    assert "google" in stats
    assert stats["google"]["recent_calls"] >= 1


@pytest.mark.asyncio
async def test_llm_rate_limiter_wait_for_slot_blocks_when_max_wait_too_small(tmp_path, monkeypatch):
    db = tmp_path / "rl3.db"
    monkeypatch.setattr(llm_rate_limiter_module.settings, "LLM_RATE_LIMIT_MAX_WAIT_SEC", 0, raising=False)
    limiter = LLMRateLimiter(sqlite_path=str(db))
    monkeypatch.setattr(
        limiter,
        "peek",
        lambda provider: RateLimitDecision(False, 12.0, "rpm_limit:openai:1"),
    )
    decision = await limiter.wait_for_slot("openai", "gpt-4o", "routine")
    assert decision.allowed is False
    assert decision.reason.startswith("rpm_limit:")
