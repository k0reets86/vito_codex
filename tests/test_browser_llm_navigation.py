import json
from unittest.mock import AsyncMock

import pytest

from modules.browser_llm_navigation import BrowserActionCandidate, suggest_browser_action


@pytest.mark.asyncio
async def test_suggest_browser_action_accepts_bounded_llm_choice():
    router = AsyncMock()
    router.call_llm = AsyncMock(
        return_value=json.dumps(
            {
                "action": "click",
                "selector": "#submit",
                "value": "",
                "confidence": 0.91,
                "reason": "primary_cta_visible",
            },
            ensure_ascii=False,
        )
    )
    result = await suggest_browser_action(
        llm_router=router,
        service="etsy",
        url="https://example.com",
        screenshot_path="/tmp/test.png",
        title="Editor",
        body_excerpt="Save as draft button is visible",
        candidates=[
            BrowserActionCandidate(action="click", selector="#submit", label="Save draft", priority=10),
            BrowserActionCandidate(action="fill", selector="#title", value="Demo", label="Title", priority=20),
        ],
    )
    assert result["action"] == "click"
    assert result["selector"] == "#submit"
    assert result["reason"] == "primary_cta_visible"


@pytest.mark.asyncio
async def test_suggest_browser_action_falls_back_on_invalid_selector():
    router = AsyncMock()
    router.call_llm = AsyncMock(
        return_value=json.dumps(
            {
                "action": "click",
                "selector": "#wrong",
                "value": "",
                "confidence": 0.88,
                "reason": "hallucinated_selector",
            },
            ensure_ascii=False,
        )
    )
    result = await suggest_browser_action(
        llm_router=router,
        service="etsy",
        url="https://example.com",
        screenshot_path="/tmp/test.png",
        title="Editor",
        body_excerpt="",
        candidates=[
            BrowserActionCandidate(action="click", selector="#submit", label="Save draft", priority=10),
            BrowserActionCandidate(action="fill", selector="#title", value="Demo", label="Title", priority=20),
        ],
    )
    assert result["action"] == "click"
    assert result["selector"] == "#submit"
    assert result["reason"] == "fallback_first_candidate"
