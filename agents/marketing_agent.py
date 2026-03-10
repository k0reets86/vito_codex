"""MarketingAgent — Agent 04: стратегия, воронки, рекламные тексты."""

import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings
from llm_router import TaskType
from modules.growth_research_operational import build_marketing_operational_pack
from modules.content_experiments import ContentExperimentEngine
from modules.growth_runtime import build_marketing_runtime_profile

logger = get_logger("marketing_agent", agent="marketing_agent")


class MarketingAgent(BaseAgent):
    NEEDS = {
        "marketing_strategy": ["research", "seo"],
        "funnel": ["marketing_strategy"],
        "ad_copy": ["seo"],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="marketing_agent", description="Маркетинговая стратегия, воронки продаж, рекламные тексты", **kwargs)
        self._cache: dict[str, str] = {}

    @property
    def capabilities(self) -> list[str]:
        return ["marketing_strategy", "funnel", "ad_copy"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "marketing_strategy":
                result = await self.create_strategy(kwargs.get("product", ""), kwargs.get("target_audience", ""), kwargs.get("budget_usd", 100))
            elif task_type == "funnel":
                result = await self.design_funnel(kwargs.get("product", kwargs.get("step", "")))
            elif task_type == "ad_copy":
                result = await self.create_ad_copy(kwargs.get("product", ""), kwargs.get("platform", "facebook"))
            else:
                result = await self.create_strategy(kwargs.get("step", task_type), "general", 100)
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_strategy(self, product: str, target_audience: str, budget_usd: float = 100) -> TaskResult:
        key = f"strategy::{(product or '').strip().lower()}::{(target_audience or '').strip().lower()}::{float(budget_usd)}"
        if key in self._cache:
            return TaskResult(success=True, output={"cached_strategy": self._cache[key]}, metadata={"cached": True})

        local = self._local_strategy(product, target_audience, budget_usd)
        op_pack = build_marketing_operational_pack(
            product=product,
            audience=target_audience,
            budget_usd=budget_usd,
            channels=local.get("channel_mix") or [],
            timeline=local.get("timeline") or [],
        )
        local["used_skills"] = op_pack["used_skills"]
        local["evidence"] = op_pack["evidence"]
        local["next_actions"] = op_pack["next_actions"]
        local["recovery_hints"] = op_pack["recovery_hints"]
        local["quality_checks"] = op_pack["quality_checks"]
        if not self.llm_router:
            self._cache[key] = str(local)
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", "marketing_runtime_profile": build_marketing_runtime_profile(product, target_audience, budget_usd), "operational_pack": op_pack, **self.get_skill_pack()})

        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=(
                f"Создай маркетинговую стратегию для продукта: {product}\n"
                f"ЦА: {target_audience}\nБюджет: ${budget_usd}\n"
                "Включи: каналы, тактики, KPI, timeline."
            ),
            estimated_tokens=3000,
        )
        if response:
            self._record_expense(0.03, f"Marketing strategy: {product[:50]}")
            local["llm_notes"] = response
        self._cache[key] = str(local)
        return TaskResult(success=True, output=local, cost_usd=0.03 if response else 0.0, metadata={"marketing_runtime_profile": build_marketing_runtime_profile(product, target_audience, budget_usd), "operational_pack": op_pack, **self.get_skill_pack()})

    async def design_funnel(self, product: str, stages: list[str] = None) -> TaskResult:
        local = self._local_funnel(product, stages)
        op_pack = build_marketing_operational_pack(
            product=product,
            audience="funnel",
            budget_usd=0,
            channels=[{"channel": "funnel_map", "focus": stage.get("stage")} for stage in local.get("stages") or []],
            timeline=[stage.get("stage", "") for stage in local.get("stages") or []],
        )
        local["used_skills"] = op_pack["used_skills"]
        local["evidence"] = op_pack["evidence"]
        local["next_actions"] = op_pack["next_actions"]
        local["recovery_hints"] = op_pack["recovery_hints"]
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", "marketing_runtime_profile": build_marketing_runtime_profile(product, "funnel", 0), "operational_pack": op_pack, **self.get_skill_pack()})
        stages_str = f"Этапы: {', '.join(stages)}" if stages else "Стандартная воронка: awareness → interest → desire → action"
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Спроектируй воронку продаж для: {product}\n{stages_str}\nОпиши каждый этап, контент, метрики.",
            estimated_tokens=2500,
        )
        if response:
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.02 if response else 0.0, metadata={"marketing_runtime_profile": build_marketing_runtime_profile(product, "funnel", 0), "operational_pack": op_pack, **self.get_skill_pack()})

    async def create_ad_copy(self, product: str, platform: str, style: str = "direct") -> TaskResult:
        local = self._local_ad_copy(product, platform, style)
        op_pack = build_marketing_operational_pack(
            product=product,
            audience=platform,
            budget_usd=0,
            channels=[{"channel": platform, "focus": "ad_copy"}],
            timeline=["copy_draft", "variant_review", "launch_test"],
        )
        local["used_skills"] = op_pack["used_skills"]
        local["evidence"] = op_pack["evidence"]
        local["next_actions"] = op_pack["next_actions"]
        local["recovery_hints"] = op_pack["recovery_hints"]
        if not self.llm_router:
            self._attach_experiment(local, product, platform)
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", "marketing_runtime_profile": build_marketing_runtime_profile(product, platform, 0), "operational_pack": op_pack, **self.get_skill_pack()})
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Напиши рекламный текст для {platform}. Продукт: {product}. Стиль: {style}. 3 варианта.",
            estimated_tokens=1500,
        )
        if response:
            local["llm_variants"] = response
        self._attach_experiment(local, product, platform)
        return TaskResult(success=True, output=local, cost_usd=0.01 if response else 0.0, metadata={"marketing_runtime_profile": build_marketing_runtime_profile(product, platform, 0), "operational_pack": op_pack, **self.get_skill_pack()})

    async def suggest_channels(self, product: str, budget_usd: float = 100) -> TaskResult:
        local = self._local_channels(product, budget_usd)
        op_pack = build_marketing_operational_pack(
            product=product,
            audience="channel_selection",
            budget_usd=budget_usd,
            channels=[{"channel": channel, "focus": "distribution"} for channel in local.get("recommended_channels") or []],
            timeline=["channel_selection", "test_plan", "budget_review"],
        )
        local["used_skills"] = op_pack["used_skills"]
        local["evidence"] = op_pack["evidence"]
        local["next_actions"] = op_pack["next_actions"]
        local["recovery_hints"] = op_pack["recovery_hints"]
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", "marketing_runtime_profile": build_marketing_runtime_profile(product, "channel_selection", budget_usd), "operational_pack": op_pack, **self.get_skill_pack()})
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Предложи лучшие маркетинговые каналы для: {product}, бюджет ${budget_usd}.",
            estimated_tokens=1500,
        )
        if response:
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.01 if response else 0.0, metadata={"marketing_runtime_profile": build_marketing_runtime_profile(product, "channel_selection", budget_usd), "operational_pack": op_pack, **self.get_skill_pack()})

    def _local_strategy(self, product: str, target_audience: str, budget_usd: float) -> dict[str, Any]:
        product_name = (product or "Digital product").strip()
        audience = (target_audience or "broad audience").strip()
        budget = max(float(budget_usd or 0), 0.0)
        paid = round(budget * 0.45, 2)
        content = round(budget * 0.35, 2)
        experiments = round(max(budget - paid - content, 0.0), 2)
        return {
            "product": product_name,
            "target_audience": audience,
            "budget_usd": budget,
            "offer_angle": f"{product_name} helps {audience} get a faster repeatable result.",
            "channel_mix": [
                {"channel": "paid_acquisition", "budget_usd": paid, "focus": "Meta/TikTok creative testing"},
                {"channel": "content_seo", "budget_usd": content, "focus": "landing page + search capture"},
                {"channel": "experiments", "budget_usd": experiments, "focus": "new hooks and A/B tests"},
            ],
            "kpis": {
                "ctr_target": ">= 1.5%",
                "landing_cr_target": ">= 2.5%",
                "cac_goal": "below target contribution margin",
            },
            "timeline": [
                "Week 1: message-market fit + baseline creatives",
                "Week 2-3: scale the best channel + retargeting",
                "Week 4: optimize funnel and cut weak ad sets",
            ],
            "validation_checklist": [
                "audience_defined",
                "offer_angle_present",
                "channel_mix_balanced",
                "timeline_defined",
            ],
            "handoff_targets": ["content_creator", "smm_agent", "email_agent", "analytics_agent"],
            "experiment_matrix": [
                {"axis": "hook", "variants": 3},
                {"axis": "creative", "variants": 2},
                {"axis": "offer_angle", "variants": 2},
            ],
        }

    def _local_funnel(self, product: str, stages: list[str] | None) -> dict[str, Any]:
        product_name = (product or "Digital product").strip()
        ordered = stages or ["awareness", "interest", "desire", "action"]
        mapped = []
        for stage in ordered:
            s = stage.strip().lower()
            if s == "awareness":
                mapped.append({"stage": "awareness", "assets": ["short videos", "hooks"], "metric": "reach/CTR"})
            elif s == "interest":
                mapped.append({"stage": "interest", "assets": ["demo", "value post", "lead magnet"], "metric": "opt-in rate"})
            elif s == "desire":
                mapped.append({"stage": "desire", "assets": ["proof", "case study", "objection handling"], "metric": "checkout starts"})
            elif s == "action":
                mapped.append({"stage": "action", "assets": ["offer", "urgency", "checkout CTA"], "metric": "conversion rate"})
            else:
                mapped.append({"stage": s, "assets": ["custom asset"], "metric": "custom metric"})
        return {
            "product": product_name,
            "stages": mapped,
            "validation_checklist": ["all_stages_mapped", "stage_metrics_present"],
            "handoff_targets": ["content_creator", "publisher_agent", "analytics_agent"],
        }

    def _local_ad_copy(self, product: str, platform: str, style: str) -> dict[str, Any]:
        p = (product or "Digital product").strip()
        net = (platform or "social").strip()
        tone = (style or "direct").strip()
        return {
            "platform": net,
            "style": tone,
            "variants": [
                f"Stop wasting time. {p} gives you a ready workflow in minutes.",
                f"Built for speed: {p} helps you launch faster and cleaner.",
                f"Get results this week with {p}. Simple setup, immediate value.",
            ],
            "validation_checklist": [
                "three_variants_present",
                "platform_named",
                "cta_angle_present",
            ],
            "handoff_targets": ["smm_agent", "quality_judge", "analytics_agent"],
        }

    def _attach_experiment(self, payload: dict[str, Any], product: str, platform: str) -> None:
        if not bool(getattr(settings, "CONTENT_AB_EXPERIMENTS_ENABLED", True)):
            return
        variants = [str(v or "").strip() for v in (payload.get("variants") or []) if str(v or "").strip()]
        if len(variants) < 2:
            return
        try:
            engine = ContentExperimentEngine(sqlite_path=settings.SQLITE_PATH)
            experiment = engine.create_experiment(
                family="marketing_copy",
                subject=str(product or "content").strip(),
                platform=str(platform or "generic").strip(),
                variants=variants,
            )
            payload["experiment"] = {
                "experiment_id": experiment["experiment_id"],
                "status": experiment["status"],
                "winner": None,
            }
        except Exception:
            return

    def _local_channels(self, product: str, budget_usd: float) -> dict[str, Any]:
        budget = max(float(budget_usd or 0), 0.0)
        if budget < 100:
            profile = "low-budget"
            channels = ["seo_long_tail", "communities", "email_capture", "creator_collabs"]
        elif budget < 1000:
            profile = "mid-budget"
            channels = ["meta_tests", "tiktok_tests", "retargeting", "seo_clusters", "newsletter_sponsorship"]
        else:
            profile = "growth-budget"
            channels = ["multi_channel_ads", "creator_network", "affiliate_program", "cro_sprint"]
        return {
            "product": (product or "Digital product").strip(),
            "budget_usd": budget,
            "budget_profile": profile,
            "recommended_channels": channels,
            "validation_checklist": ["budget_profile_selected", "channels_ranked"],
            "handoff_targets": ["smm_agent", "email_agent", "analytics_agent"],
        }
