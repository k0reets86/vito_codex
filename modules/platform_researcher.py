from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from config.logger import get_logger
from config.paths import PROJECT_ROOT

logger = get_logger("platform_researcher", agent="platform_researcher")

RESEARCH_PROMPT = """
Ты исследуешь платформу "{platform_name}" для автономного AI-агента VITO.

СОБРАННЫЕ ДАННЫЕ:
{raw_data}

Заполни следующий JSON профиль платформы. Если данных нет — оставь null.
Отвечай ТОЛЬКО валидным JSON:
{schema_template}
""".strip()


class PlatformResearcher:
    def __init__(
        self,
        browser_agent=None,
        research_agent=None,
        llm_caller: Callable[[str], Awaitable[str]] | None = None,
    ):
        self.browser = browser_agent
        self.researcher = research_agent
        self.llm = llm_caller

    async def research(self, platform_name: str, platform_url: str | None = None) -> dict:
        logger.info(f"Researching platform: {platform_name}", extra={"event": "platform_research_start"})
        raw: dict[str, Any] = {}
        url = platform_url or f"https://{self._slug(platform_name)}.com"
        raw["homepage"] = await self._fetch_homepage(url)
        raw["api_docs"] = await self._find_api_docs(platform_name, url)
        raw["rules"] = await self._find_rules(platform_name, url)
        raw["community"] = await self._research_community(platform_name)
        raw["reviews"] = await self._find_reviews(platform_name)
        raw["github"] = await self._find_github_integrations(platform_name)
        profile = await self._structure_with_llm(platform_name, url, raw)
        if not isinstance(profile, dict):
            profile = {}
        profile.setdefault("id", self._slug(platform_name))
        profile.setdefault("name", platform_name)
        profile.setdefault("url", url)
        profile.setdefault("status", "researching")
        profile.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        research = profile.setdefault("research", {})
        if not isinstance(research, dict):
            research = {}
            profile["research"] = research
        research["sources_consulted"] = list(raw.keys())
        research["last_updated"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Platform research complete: {platform_name}", extra={"event": "platform_research_complete"})
        return profile

    async def _fetch_homepage(self, url: str) -> str:
        if not self.browser:
            return ""
        try:
            if hasattr(self.browser, "navigate"):
                nav = await self.browser.navigate(url, service="")
                if nav and not getattr(nav, "success", False):
                    return ""
            if hasattr(self.browser, "extract_text"):
                txt = await self.browser.extract_text(url, "body", service="")
                if txt and getattr(txt, "success", False):
                    return str(txt.output)[:2000]
            return ""
        except Exception as e:
            logger.warning(f"Homepage fetch failed: {e}", extra={"event": "platform_homepage_fetch_failed"})
            return ""

    async def _find_api_docs(self, name: str, base_url: str) -> dict:
        result = {"available": False, "url": None, "summary": ""}
        api_paths = ["/api/docs", "/developers", "/api", "/developer", "/docs/api"]
        for path in api_paths:
            try:
                candidate = base_url.rstrip("/") + path
                text = await self._browser_text(candidate)
                low = text.lower()
                if any(w in low for w in ("endpoint", "authentication", "rate limit", "api key", "oauth")):
                    result["available"] = True
                    result["url"] = candidate
                    result["summary"] = text[:1500]
                    break
            except Exception:
                continue
        if not result["available"] and self.researcher:
            r = await self._research_query(f"{name} API documentation developers")
            result["summary"] = r[:1000]
            result["available"] = "api" in r.lower() or "oauth" in r.lower()
        return result

    async def _find_rules(self, name: str, base_url: str) -> str:
        rule_paths = ["/terms", "/legal", "/seller-policy", "/help/policies", "/guidelines"]
        texts: list[str] = []
        for path in rule_paths[:3]:
            try:
                text = await self._browser_text(base_url.rstrip("/") + path)
                if text and len(text) > 100:
                    texts.append(text[:800])
            except Exception:
                continue
        if not texts and self.researcher:
            texts.append((await self._research_query(f"{name} seller guidelines rules"))[:800])
        return " | ".join(x for x in texts if x)

    async def _research_community(self, name: str) -> str:
        if not self.researcher:
            return ""
        queries = [
            f"{name} seller experience review 2024 2025",
            f"{name} pros cons honest review seller",
            f"site:reddit.com {name} sell digital products experience",
        ]
        results: list[str] = []
        for q in queries:
            r = await self._research_query(q)
            if r:
                results.append(r[:500])
            await asyncio.sleep(0)
        return " | ".join(results)

    async def _find_reviews(self, name: str) -> str:
        return (await self._research_query(f"{name} platform review rating trustpilot g2 capterra 2025"))[:600]

    async def _find_github_integrations(self, name: str) -> str:
        return (await self._research_query(f"{name} python library SDK github integration wrapper"))[:600]

    async def _structure_with_llm(self, platform_name: str, url: str, raw: dict) -> dict:
        template = (PROJECT_ROOT / "data" / "platform_profiles" / "template.json").read_text(encoding="utf-8")
        if not self.llm:
            return self._fallback_profile(platform_name, url, raw)
        prompt = RESEARCH_PROMPT.format(
            platform_name=platform_name,
            raw_data=json.dumps(raw, ensure_ascii=False)[:4000],
            schema_template=template[:2500],
        )
        try:
            response = await self.llm(prompt)
            m = re.search(r"\{.*\}", response or "", re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return self._fallback_profile(platform_name, url, raw)

    async def _browser_text(self, url: str) -> str:
        if not self.browser:
            return ""
        if hasattr(self.browser, "navigate"):
            await self.browser.navigate(url, service="")
        if hasattr(self.browser, "extract_text"):
            result = await self.browser.extract_text(url, "body", service="")
            if result and getattr(result, "success", False):
                return str(result.output or "")
        return ""

    async def _research_query(self, query: str) -> str:
        if not self.researcher:
            return ""
        try:
            if hasattr(self.researcher, "ask"):
                result = await self.researcher.ask("research", query=query)
                if hasattr(result, "output"):
                    return str(result.output or "")
                return str(result or "")
        except Exception:
            pass
        return ""

    @staticmethod
    def _slug(name: str) -> str:
        return re.sub(r"[^a-z0-9_]+", "_", str(name or "").strip().lower()).strip("_") or "platform"

    def _fallback_profile(self, platform_name: str, url: str, raw: dict) -> dict:
        template = json.loads((PROJECT_ROOT / "data" / "platform_profiles" / "template.json").read_text(encoding="utf-8"))
        template["id"] = self._slug(platform_name)
        template["name"] = platform_name
        template["url"] = url
        template["status"] = "researching"
        template["created_at"] = datetime.now(timezone.utc).isoformat()
        template["research"]["user_reviews_summary"] = str(raw.get("community") or "")[:1000]
        template["overview"]["description"] = str(raw.get("homepage") or "")[:500]
        return template
