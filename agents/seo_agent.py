"""SEOAgent — Agent 06: SEO-оптимизация и keyword research."""

import json
import re
import time

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.listing_optimizer import optimize_listing_payload

logger = get_logger("seo_agent", agent="seo_agent")


class SEOAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="seo_agent", description="SEO-оптимизация, keyword research, мета-теги", **kwargs)
        self._cache: dict[str, str] = {}

    @property
    def capabilities(self) -> list[str]:
        return ["seo", "keyword_research", "listing_seo_pack"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "keyword_research":
                result = await self.keyword_research(kwargs.get("topic", kwargs.get("step", "")))
            elif task_type == "seo":
                result = await self.optimize_content(kwargs.get("content", ""), kwargs.get("keywords", []))
            elif task_type == "generate_meta":
                result = await self.generate_meta(kwargs.get("content", ""), kwargs.get("keywords", []))
            elif task_type == "listing_seo_pack":
                result = await self.listing_seo_pack(
                    platform=kwargs.get("platform", "gumroad"),
                    title=kwargs.get("title", kwargs.get("topic", "")),
                    description=kwargs.get("description", kwargs.get("content", "")),
                    tags=kwargs.get("tags", []),
                )
            else:
                result = await self.keyword_research(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def keyword_research(self, topic: str, language: str = "en") -> TaskResult:
        key = f"kw::{language}::{(topic or '').strip().lower()}"
        if key in self._cache:
            return TaskResult(success=True, output=self._cache[key], metadata={"cached": True})

        base = self._local_keyword_research(topic, language=language)
        response = None
        cost = 0.0
        if self.llm_router:
            response = await self._call_llm(
                task_type=TaskType.RESEARCH,
                prompt=(
                    f"Keyword research для: {topic} (язык: {language}). "
                    "Верни 10 primary keywords, 10 long-tail, 5 LSI. Без воды."
                ),
                estimated_tokens=1200,
            )
        output = response or base
        if response:
            cost = 0.01
            self._record_expense(cost, f"Keyword research: {topic[:50]}")
        self._cache[key] = output
        return TaskResult(success=True, output=output, cost_usd=cost)

    async def optimize_content(self, content: str, keywords: list[str]) -> TaskResult:
        local = self._local_optimize_content(content, keywords)
        if not self.llm_router:
            return TaskResult(success=True, output=local)
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Оптимизируй контент для SEO. Keywords: {', '.join(keywords)}\n\nКонтент:\n{content[:5000]}",
            estimated_tokens=2200,
        )
        if not response:
            return TaskResult(success=True, output=local)
        self._record_expense(0.01, "SEO optimize content")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def analyze_rankings(self, url: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(
            task_type=TaskType.RESEARCH,
            prompt=f"Проанализируй SEO для URL: {url}. Оцени on-page факторы, дай рекомендации.",
            estimated_tokens=2000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def generate_meta(self, content: str, keywords: list[str]) -> TaskResult:
        local = self._local_meta(content, keywords)
        if not self.llm_router:
            return TaskResult(success=True, output=json.dumps(local, ensure_ascii=False))
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=(
                "Сгенерируй SEO мета-теги (title <=60, description <=160) для:\n"
                f"{content[:3000]}\nKeywords: {', '.join(keywords)}"
            ),
            estimated_tokens=900,
        )
        if not response:
            return TaskResult(success=True, output=json.dumps(local, ensure_ascii=False))
        return TaskResult(success=True, output=response, cost_usd=0.005)

    def _local_keyword_research(self, topic: str, language: str = "en") -> str:
        tokens = [t for t in re.split(r"[^a-zA-Z0-9а-яА-Я]+", (topic or "").lower()) if len(t) > 2]
        seed = " ".join(tokens[:4]) or "digital product"
        primary = [seed, f"{seed} ideas", f"{seed} guide", f"best {seed}", f"{seed} examples"]
        long_tail = [
            f"how to start with {seed}",
            f"{seed} for beginners",
            f"best tools for {seed}",
            f"{seed} templates download",
            f"profitable {seed} niche",
        ]
        lsi = [f"{seed} strategy", f"{seed} checklist", f"{seed} workflow", f"{seed} trends", f"{seed} tips"]
        return (
            f"PRIMARY ({language}):\n- " + "\n- ".join(primary)
            + "\n\nLONG_TAIL:\n- " + "\n- ".join(long_tail)
            + "\n\nLSI:\n- " + "\n- ".join(lsi)
        )

    def _local_optimize_content(self, content: str, keywords: list[str]) -> str:
        body = (content or "").strip() or "(empty content)"
        keys = [k.strip() for k in (keywords or []) if str(k).strip()][:8]
        lines = ["SEO Optimization (local fallback):"]
        if keys:
            lines.append("- Target keywords: " + ", ".join(keys))
        lines.append("- Add 1 keyword in H1, 1 in first paragraph, 2-3 naturally in body.")
        lines.append("- Keep sentence length short and include one bullet list.")
        lines.append("\nReworked draft:\n" + body[:3000])
        return "\n".join(lines)

    def _local_meta(self, content: str, keywords: list[str]) -> dict[str, str]:
        clean = re.sub(r"\s+", " ", (content or "")).strip()
        kw = (keywords[0] if keywords else "Digital Product").strip()[:30]
        title = f"{kw} Guide | Actionable Steps"[:60]
        desc_base = clean[:120] if clean else f"Learn {kw} with practical steps and templates."
        description = (desc_base + " Start now.")[:160]
        return {"title": title, "description": description}

    async def listing_seo_pack(self, platform: str, title: str, description: str, tags: list[str] | None = None) -> TaskResult:
        payload = optimize_listing_payload(
            platform,
            {
                "title": title,
                "description": description,
                "tags": tags or [],
            },
        )
        pack = {
            "platform": platform,
            "title": payload.get("title"),
            "short_description": payload.get("short_description"),
            "long_description": payload.get("description"),
            "tags": payload.get("tags"),
            "seo_title": payload.get("seo_title"),
            "seo_description": payload.get("seo_description"),
            "keywords": payload.get("keywords", [])[:20],
            "category": payload.get("category"),
            "seo_score": payload.get("seo_score"),
            "publish_ready": payload.get("publish_ready"),
        }
        return TaskResult(success=True, output=pack)
