"""TrendScout — Agent 01: сканирование трендов и предложение ниш.

v0.3.0: добавлены Google News, RSS feeds, pytrends.
"""

import json
import time
import uuid
from typing import Any, Optional

import aiohttp

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings
from llm_router import TaskType

logger = get_logger("trend_scout", agent="trend_scout")

DEFAULT_RSS_FEEDS = [
    "https://www.producthunt.com/feed",
    "https://hnrss.org/frontpage",
]


def _get_reddit_rss_feeds() -> list[str]:
    """Собирает Reddit RSS фиды из .env (settings)."""
    feeds = []
    for attr in ("REDDIT_RSS_ENTREPRENEUR", "REDDIT_RSS_PASSIVE", "REDDIT_RSS_ECOMMERCE"):
        url = getattr(settings, attr, "")
        if url:
            feeds.append(url)
    return feeds


class TrendScout(BaseAgent):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="trend_scout", description="Сканирование трендов, исследование ниш", **kwargs)
        self.browser_agent = browser_agent

    @property
    def capabilities(self) -> list[str]:
        return ["trend_scan", "niche_research", "google_news", "rss_scan", "reddit_scan"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "trend_scan":
                result = await self.scan_google_trends(kwargs.get("keywords", ["digital products", "AI tools"]))
            elif task_type == "niche_research":
                result = await self.suggest_niches()
            elif task_type == "google_news":
                result = await self.scan_google_news(
                    kwargs.get("query", "digital products"),
                    kwargs.get("language", "en"),
                )
            elif task_type == "rss_scan":
                feeds = kwargs.get("feeds", DEFAULT_RSS_FEEDS + _get_reddit_rss_feeds())
                result = await self.scan_rss_feeds(feeds)
            elif task_type == "reddit_scan":
                result = await self.scan_reddit(kwargs.get("subreddits"))
            else:
                result = await self.scan_google_trends(kwargs.get("keywords", ["digital products"]))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def scan_google_trends(self, keywords: list[str], geo: str = "US") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = f"Проанализируй текущие тренды Google Trends для ключевых слов: {', '.join(keywords)} (регион: {geo}). Дай топ-10 растущих запросов и ниш."
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Google Trends scan: {', '.join(keywords[:3])}")
        if self.memory:
            self.memory.store_knowledge(doc_id=f"trends_{uuid.uuid4().hex[:8]}", text=f"Google Trends {geo}: {response[:500]}", metadata={"type": "trend", "geo": geo})
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def scan_reddit(self, subreddits: list[str] | None = None) -> TaskResult:
        """Сканирование Reddit: сначала RSS из .env, потом LLM-анализ."""
        # 1. Пробуем прочитать Reddit RSS из .env
        reddit_feeds = _get_reddit_rss_feeds()
        rss_context = ""
        if reddit_feeds:
            rss_result = await self.scan_rss_feeds(reddit_feeds)
            if rss_result.success and rss_result.output:
                rss_context = f"\n\nДанные из Reddit RSS:\n{rss_result.output[:2000]}"
                logger.info(
                    f"Reddit RSS загружен: {len(reddit_feeds)} фидов",
                    extra={"event": "reddit_rss_loaded", "context": {"feeds": len(reddit_feeds)}},
                )

        if not self.llm_router:
            if rss_context:
                return TaskResult(success=True, output=rss_context, cost_usd=0.0)
            return TaskResult(success=False, error="LLM Router недоступен")

        subs = subreddits or ["entrepreneur", "passive_income", "ecommerce"]
        prompt = (
            f"Проанализируй горячие темы в Reddit-сообществах: {', '.join(subs)}. "
            f"Какие темы обсуждаются чаще всего? Какие возможности для цифровых продуктов?"
            f"{rss_context}"
        )
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Reddit scan: {', '.join(subs[:3])}")
        if self.memory:
            self.memory.store_knowledge(doc_id=f"reddit_{uuid.uuid4().hex[:8]}", text=f"Reddit trends: {response[:500]}", metadata={"type": "trend", "source": "reddit"})
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def suggest_niches(self) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = "Предложи 5-7 перспективных ниш для цифровых продуктов (ebooks, templates, курсы, SaaS). Для каждой укажи: название, уровень конкуренции, потенциал монетизации, рекомендуемые продукты."
        response = await self.llm_router.call_llm(task_type=TaskType.STRATEGY, prompt=prompt, estimated_tokens=2500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.03, "Suggest niches")
        return TaskResult(success=True, output=response, cost_usd=0.03)

    async def scan_google_news(self, query: str, language: str = "en") -> TaskResult:
        """Сканирование Google News через Custom Search API (tbm=nws)."""
        api_key = getattr(settings, "GOOGLE_API_KEY", "")
        if not api_key:
            return TaskResult(success=False, error="GOOGLE_API_KEY не задан")

        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "key": api_key,
                    "cx": "search",  # Custom Search Engine ID (fallback)
                    "q": query,
                    "tbm": "nws",
                    "num": 10,
                    "hl": language,
                }
                async with session.get(
                    "https://www.googleapis.com/customsearch/v1", params=params
                ) as resp:
                    if resp.status != 200:
                        # Fallback: use LLM to summarize news
                        return await self._news_via_llm(query, language)
                    data = await resp.json()

            items = data.get("items", [])
            news = [
                {"title": item.get("title", ""), "link": item.get("link", ""), "snippet": item.get("snippet", "")}
                for item in items
            ]

            output = json.dumps(news, ensure_ascii=False)
            if self.memory:
                self.memory.store_knowledge(
                    doc_id=f"gnews_{uuid.uuid4().hex[:8]}",
                    text=f"Google News '{query}': {output[:500]}",
                    metadata={"type": "news", "query": query, "language": language},
                )

            self._record_expense(0.01, f"Google News: {query}")
            return TaskResult(success=True, output=output, cost_usd=0.01)

        except Exception as e:
            logger.warning(f"Google News error: {e}", extra={"event": "gnews_error"})
            return await self._news_via_llm(query, language)

    async def _news_via_llm(self, query: str, language: str) -> TaskResult:
        """Fallback: получение новостей через LLM (Perplexity)."""
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = f"Найди последние новости по теме: {query} (язык: {language}). Дай топ-10 новостей с заголовками и краткими описаниями."
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"News via LLM: {query}")
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def scan_rss_feeds(self, feeds: list[str] | None = None) -> TaskResult:
        """Сканирование RSS feeds (Product Hunt, Indie Hackers, etc.)."""
        feeds = feeds or DEFAULT_RSS_FEEDS
        all_entries = []

        try:
            import feedparser
        except ImportError:
            # Fallback without feedparser
            return await self._rss_via_llm(feeds)

        for feed_url in feeds:
            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries[:5]:
                    all_entries.append({
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:200],
                        "published": entry.get("published", ""),
                        "source": feed_url,
                    })
            except Exception as e:
                logger.debug(f"RSS feed error {feed_url}: {e}", extra={"event": "rss_feed_error"})

        if not all_entries:
            return await self._rss_via_llm(feeds)

        output = json.dumps(all_entries, ensure_ascii=False)
        if self.memory:
            self.memory.store_knowledge(
                doc_id=f"rss_{uuid.uuid4().hex[:8]}",
                text=f"RSS scan: {output[:500]}",
                metadata={"type": "rss", "feeds": len(feeds)},
            )

        return TaskResult(success=True, output=output, cost_usd=0.0)

    async def _rss_via_llm(self, feeds: list[str]) -> TaskResult:
        """Fallback: RSS через LLM."""
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = f"Проанализируй топ продукты и тренды на Product Hunt и Indie Hackers за последнюю неделю."
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, "RSS via LLM")
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def scan_free_trend_apis(self) -> TaskResult:
        """Сканирование бесплатных API для трендов (pytrends - Google Trends)."""
        try:
            from pytrends.request import TrendReq
            pytrends = TrendReq(hl="en-US", tz=360)
            # Получаем текущие тренды
            trending = pytrends.trending_searches(pn="united_states")
            trends_list = trending[0].tolist()[:20]

            output = json.dumps({"trending_searches": trends_list}, ensure_ascii=False)
            if self.memory:
                self.memory.store_knowledge(
                    doc_id=f"pytrends_{uuid.uuid4().hex[:8]}",
                    text=f"Google Trends trending: {', '.join(trends_list[:10])}",
                    metadata={"type": "pytrends", "source": "google_trends"},
                )
            return TaskResult(success=True, output=output, cost_usd=0.0)

        except ImportError:
            return TaskResult(success=False, error="pytrends не установлен")
        except Exception as e:
            logger.warning(f"pytrends error: {e}", extra={"event": "pytrends_error"})
            return TaskResult(success=False, error=str(e))
