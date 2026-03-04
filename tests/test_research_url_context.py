import pytest

from modules.research_url_context import ResearchURLContextPipeline, SourceTrace


def test_extract_urls_unique_and_limited():
    p = ResearchURLContextPipeline()
    text = "a https://a.com/x b https://b.com c https://a.com/x"
    urls = p.extract_urls(text, limit=2)
    assert urls == ["https://a.com/x", "https://b.com"]


def test_append_sources_adds_block():
    answer = "Готово. Ниже анализ."
    traces = [
        SourceTrace(url="https://a.com", title="A", excerpt="ok", status="ok"),
        SourceTrace(url="https://b.com", title="B", excerpt="ok", status="ok"),
    ]
    out = ResearchURLContextPipeline.append_sources(answer, traces)
    assert "Источники:" in out
    assert "https://a.com" in out
    assert "https://b.com" in out


@pytest.mark.asyncio
async def test_enrich_prompt_without_urls_no_changes():
    p = ResearchURLContextPipeline()
    prompt = "без ссылок"
    out, traces = await p.enrich_prompt(prompt)
    assert out == prompt
    assert traces == []
