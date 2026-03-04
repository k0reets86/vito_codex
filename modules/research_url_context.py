"""Research URL-context pipeline with source trace for owner-facing responses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Optional

import aiohttp

from config.logger import get_logger
from config.settings import settings

logger = get_logger("research_url_context", agent="research_url_context")


@dataclass
class SourceTrace:
    url: str
    title: str = ""
    excerpt: str = ""
    status: str = "ok"
    error: str = ""


class ResearchURLContextPipeline:
    @staticmethod
    def extract_urls(text: str, limit: Optional[int] = None) -> list[str]:
        urls = re.findall(r"https?://[^\s<>\"]+", str(text or ""))
        out: list[str] = []
        seen: set[str] = set()
        for u in urls:
            clean = u.rstrip(").,;")
            if clean and clean not in seen:
                seen.add(clean)
                out.append(clean)
            if limit and len(out) >= limit:
                break
        return out

    @staticmethod
    def _strip_html(html: str) -> tuple[str, str]:
        raw = str(html or "")
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
        title = unescape(m.group(1)).strip() if m else ""
        no_scripts = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        text = re.sub(r"(?is)<[^>]+>", " ", no_scripts)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return title, text

    async def _fetch_one(self, session: aiohttp.ClientSession, url: str, max_chars: int) -> SourceTrace:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=12), allow_redirects=True) as resp:
                if resp.status >= 400:
                    return SourceTrace(url=url, status="error", error=f"http_{resp.status}")
                html = await resp.text(errors="ignore")
                title, text = self._strip_html(html)
                if not text:
                    return SourceTrace(url=url, title=title, status="error", error="empty_body")
                return SourceTrace(url=url, title=title, excerpt=text[:max_chars], status="ok")
        except Exception as e:
            return SourceTrace(url=url, status="error", error=str(e)[:160])

    async def enrich_prompt(self, prompt: str) -> tuple[str, list[SourceTrace]]:
        if not bool(getattr(settings, "RESEARCH_URL_CONTEXT_ENABLED", True)):
            return prompt, []
        max_urls = max(1, int(getattr(settings, "RESEARCH_URL_CONTEXT_MAX_URLS", 4) or 4))
        max_chars = max(200, int(getattr(settings, "RESEARCH_URL_CONTEXT_MAX_CHARS_PER_URL", 2500) or 2500))
        urls = self.extract_urls(prompt, limit=max_urls)
        if not urls:
            return prompt, []
        traces: list[SourceTrace] = []
        async with aiohttp.ClientSession() as session:
            for u in urls:
                traces.append(await self._fetch_one(session, u, max_chars=max_chars))
        ok = [t for t in traces if t.status == "ok" and t.excerpt]
        if not ok:
            return prompt, traces
        blocks = []
        for i, t in enumerate(ok, start=1):
            title = t.title or "(no title)"
            blocks.append(f"[SRC{i}] URL: {t.url}\nTitle: {title}\nExcerpt:\n{t.excerpt}")
        addition = (
            "\n\n[URL_CONTEXT_PIPELINE]\n"
            "Ниже — содержимое URL, загруженное напрямую. "
            "Используй эти фрагменты как приоритетный источник фактов.\n\n"
            + "\n\n".join(blocks)
            + "\n[/URL_CONTEXT_PIPELINE]\n"
        )
        logger.info(
            "Research URL context enriched",
            extra={"event": "research_url_context_enriched", "context": {"urls": len(urls), "ok": len(ok)}},
        )
        return f"{prompt}{addition}", traces

    @staticmethod
    def append_sources(answer: str, traces: list[SourceTrace]) -> str:
        text = str(answer or "").strip()
        if not text:
            return text
        if "источники:" in text.lower():
            return text
        ok = [t for t in (traces or []) if t.status == "ok"]
        if not ok:
            return text
        lines = ["", "Источники:"]
        for i, t in enumerate(ok, start=1):
            title = t.title.strip() if t.title else "source"
            lines.append(f"{i}. {title} — {t.url}")
        return text + "\n" + "\n".join(lines)
