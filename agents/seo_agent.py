"""SEOAgent — Agent 06: SEO-оптимизация и keyword research."""

import json
import re
import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.growth_runtime import build_seo_runtime_profile
from modules.listing_optimizer import optimize_listing_payload

logger = get_logger("seo_agent", agent="seo_agent")


class SEOAgent(BaseAgent):
    NEEDS = {
        "keyword_research": ["research"],
        "seo": ["content_pipeline"],
        "generate_meta": ["seo"],
        "listing_seo_pack": ["listing_create"],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="seo_agent", description="SEO-оптимизация, keyword research, мета-теги", **kwargs)
        self._cache: dict[str, str] = {}

    @property
    def capabilities(self) -> list[str]:
        return ["seo", "keyword_research", "listing_seo_pack", "generate_meta"]

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
            cached = self._safe_json_loads(self._cache[key]) or {"raw": self._cache[key]}
            return TaskResult(success=True, output=cached, metadata={"cached": True})

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
        output = dict(base)
        if response:
            cost = 0.01
            self._record_expense(cost, f"Keyword research: {topic[:50]}")
            output["llm_notes"] = str(response)
        output["recovery_hints"] = [
            "If keyword set feels too generic, rerun with narrower audience or platform-specific modifier.",
            "Prefer long-tail terms when direct commercial terms are too competitive.",
        ]
        output["evidence"] = {
            "primary_count": len(output.get("primary_keywords", []) or []),
            "long_tail_count": len(output.get("long_tail_keywords", []) or []),
            "lsi_count": len(output.get("lsi_keywords", []) or []),
        }
        self._cache[key] = json.dumps(output, ensure_ascii=False)
        return TaskResult(
            success=True,
            output=output,
            cost_usd=cost,
            metadata={
                "seo_runtime_profile": build_seo_runtime_profile(
                    platform="research",
                    topic=str(topic or ""),
                    keywords=output.get("primary_keywords"),
                    seo_score=None,
                    publish_ready=False,
                ),
                **self.get_skill_pack(),
            },
        )

    async def optimize_content(self, content: str, keywords: list[str]) -> TaskResult:
        local = self._local_optimize_content(content, keywords)
        if not self.llm_router:
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "seo_runtime_profile": build_seo_runtime_profile(
                        platform="content",
                        topic=str((keywords or ["content"])[0] if keywords else "content"),
                        keywords=keywords,
                        seo_score=local.get("seo_readiness"),
                        publish_ready=False,
                    ),
                    **self.get_skill_pack(),
                },
            )
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Оптимизируй контент для SEO. Keywords: {', '.join(keywords)}\n\nКонтент:\n{content[:5000]}",
            estimated_tokens=2200,
        )
        if not response:
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "seo_runtime_profile": build_seo_runtime_profile(
                        platform="content",
                        topic=str((keywords or ["content"])[0] if keywords else "content"),
                        keywords=keywords,
                        seo_score=local.get("seo_readiness"),
                        publish_ready=False,
                    ),
                    **self.get_skill_pack(),
                },
            )
        self._record_expense(0.01, "SEO optimize content")
        local["llm_rewrite"] = response
        local["recovery_hints"] = [
            "Re-check title/H1 keyword placement if readiness stays below target.",
            "Shorten meta text if SERP snippets exceed length budgets.",
        ]
        return TaskResult(
            success=True,
            output=local,
            cost_usd=0.01,
            metadata={
                "seo_runtime_profile": build_seo_runtime_profile(
                    platform="content",
                    topic=str((keywords or ["content"])[0] if keywords else "content"),
                    keywords=keywords,
                    seo_score=local.get("seo_readiness"),
                    publish_ready=False,
                ),
                **self.get_skill_pack(),
            },
        )

    async def analyze_rankings(self, url: str) -> TaskResult:
        local = {
            "url": url,
            "status": "review_required",
            "checks": ["title", "meta_description", "headers", "internal_links", "indexability"],
        }
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.RESEARCH,
            prompt=f"Проанализируй SEO для URL: {url}. Оцени on-page факторы, дай рекомендации.",
            estimated_tokens=2000,
        )
        if response:
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.01 if response else 0.0)

    async def generate_meta(self, content: str, keywords: list[str]) -> TaskResult:
        local = self._local_meta(content, keywords)
        if not self.llm_router:
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "seo_runtime_profile": build_seo_runtime_profile(
                        platform="meta",
                        topic=str((keywords or ["meta"])[0] if keywords else "meta"),
                        keywords=keywords,
                        seo_score=None,
                        publish_ready=True,
                    ),
                    **self.get_skill_pack(),
                },
            )
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=(
                "Сгенерируй SEO мета-теги (title <=60, description <=160) для:\n"
                f"{content[:3000]}\nKeywords: {', '.join(keywords)}"
            ),
            estimated_tokens=900,
        )
        if not response:
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "seo_runtime_profile": build_seo_runtime_profile(
                        platform="meta",
                        topic=str((keywords or ["meta"])[0] if keywords else "meta"),
                        keywords=keywords,
                        seo_score=None,
                        publish_ready=True,
                    ),
                    **self.get_skill_pack(),
                },
            )
        meta = self._safe_json_loads(response)
        if isinstance(meta, dict):
            local.update({k: str(v) for k, v in meta.items() if str(v).strip()})
        else:
            local["llm_notes"] = response
        return TaskResult(
            success=True,
            output=local,
            cost_usd=0.005,
            metadata={
                "seo_runtime_profile": build_seo_runtime_profile(
                    platform="meta",
                    topic=str((keywords or ["meta"])[0] if keywords else "meta"),
                    keywords=keywords,
                    seo_score=None,
                    publish_ready=True,
                ),
                **self.get_skill_pack(),
            },
        )

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
            "evidence": {
                "title_len": len(str(payload.get("title") or "")),
                "description_len": len(str(payload.get("description") or "")),
                "tag_count": len(payload.get("tags") or []),
                "keyword_count": len(payload.get("keywords") or []),
            },
            "recovery_hints": [
                "Trim title if platform truncates the main value proposition.",
                "If tags are blocked, retry with shorter long-tail phrases.",
                "If category is weak, rerun listing optimizer with platform-specific intent.",
            ],
        }
        pack["handoff_targets"] = ["ecommerce_agent", "publisher_agent"] if pack.get("publish_ready") else ["content_creator", "marketing_agent"]
        return TaskResult(
            success=True,
            output=pack,
            metadata={
                "seo_runtime_profile": build_seo_runtime_profile(
                    platform=platform,
                    topic=str(title or ""),
                    keywords=pack.get("keywords"),
                    seo_score=pack.get("seo_score"),
                    publish_ready=pack.get("publish_ready"),
                ),
                **self.get_skill_pack(),
            },
        )

    def _local_keyword_research(self, topic: str, language: str = "en") -> dict[str, Any]:
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
        return {
            "topic": topic,
            "language": language,
            "primary_keywords": primary,
            "long_tail_keywords": long_tail,
            "lsi_keywords": lsi,
            "search_intent": "commercial_informational",
            "recommended_usage": {
                "title": primary[:2],
                "tags": long_tail[:5],
                "body": lsi[:5],
            },
        }

    def _local_optimize_content(self, content: str, keywords: list[str]) -> dict[str, Any]:
        body = (content or "").strip() or "(empty content)"
        keys = [k.strip() for k in (keywords or []) if str(k).strip()][:8]
        return {
            "target_keywords": keys,
            "recommended_changes": [
                "Add one target keyword to H1",
                "Place one target keyword in the first paragraph",
                "Use 2-3 target keywords naturally in the body",
                "Add one bullet list for scanability",
                "Keep average sentence length short",
            ],
            "draft_preview": body[:3000],
            "seo_readiness": 72 if keys else 48,
        }

    def _local_meta(self, content: str, keywords: list[str]) -> dict[str, str]:
        clean = re.sub(r"\s+", " ", (content or "")).strip()
        kw = (keywords[0] if keywords else "Digital Product").strip()[:30]
        title = f"{kw} Guide | Actionable Steps"[:60]
        desc_base = clean[:120] if clean else f"Learn {kw} with practical steps and templates."
        description = (desc_base + " Start now.")[:160]
        return {"title": title, "description": description}

    def _safe_json_loads(self, value: str) -> dict[str, Any] | None:
        try:
            data = json.loads(str(value or "").strip())
        except Exception:
            return None
        return data if isinstance(data, dict) else None
