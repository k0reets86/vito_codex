#!/usr/bin/env python3
"""Mega audit for all VITO agents.

Checks:
1) Static combat score from source code (capabilities, branching, method depth).
2) Runtime smoke execution for each agent on at least one declared capability.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.account_manager import AccountManager
from agents.agent_registry import AgentRegistry
from agents.analytics_agent import AnalyticsAgent
from agents.base_agent import BaseAgent, TaskResult
from agents.browser_agent import BrowserAgent
from agents.content_creator import ContentCreator
from agents.devops_agent import DevOpsAgent
from agents.document_agent import DocumentAgent
from agents.ecommerce_agent import ECommerceAgent
from agents.economics_agent import EconomicsAgent
from agents.email_agent import EmailAgent
from agents.hr_agent import HRAgent
from agents.legal_agent import LegalAgent
from agents.marketing_agent import MarketingAgent
from agents.partnership_agent import PartnershipAgent
from agents.publisher_agent import PublisherAgent
from agents.quality_judge import QualityJudge
from agents.research_agent import ResearchAgent
from agents.risk_agent import RiskAgent
from agents.security_agent import SecurityAgent
from agents.seo_agent import SEOAgent
from agents.smm_agent import SMMAgent
from agents.translation_agent import TranslationAgent
from agents.trend_scout import TrendScout
from agents.vito_core import VITOCore


class DummyLLMRouter:
    async def call_llm(self, *args, **kwargs):
        prompt = (kwargs.get("prompt") or "").lower()
        if "верни json" in prompt and "score" in prompt and "issues" in prompt:
            return '{"score": 8, "feedback": "Good baseline quality for publish flow", "issues": []}'
        if kwargs.get("estimated_tokens", 0) <= 150:
            return "en"
        return "Stub response: operational output."

    def check_daily_limit(self) -> bool:
        return True

    def get_daily_spend(self) -> float:
        return 0.0


class DummyMemory:
    def store_knowledge(self, *args, **kwargs):
        return None

    def save_skill(self, *args, **kwargs):
        return None

    def update_skill_last_result(self, *args, **kwargs):
        return None

    def save_pattern(self, *args, **kwargs):
        return None

    def search_skills(self, *args, **kwargs):
        return []

    def search_knowledge(self, *args, **kwargs):
        return []

    def log_error(self, *args, **kwargs):
        return None


class DummyFinance:
    def record_expense(self, *args, **kwargs):
        return None

    def check_expense(self, *args, **kwargs):
        return {"allowed": True, "action": "allow"}

    def get_daily_spend(self) -> float:
        return 0.0

    def get_daily_revenue(self) -> float:
        return 0.0


class DummyPlatform:
    def __init__(self, name: str):
        self.name = name

    async def authenticate(self) -> bool:
        return True

    async def publish(self, content: dict) -> dict:
        platform = str(self.name or "").strip().lower()
        payload = dict(content or {})
        title = str(payload.get("name") or payload.get("title") or "Mega test product").strip() or "Mega test product"
        slug = title.lower().replace(" ", "-")[:32] or f"{platform}-item"
        base = {
            "platform": platform,
            "content_preview": str(content)[:120],
            "handled_by": f"dummy_{platform}",
        }
        if platform == "gumroad":
            base.update(
                {
                    "status": "published",
                    "id": f"{platform}_{slug}",
                    "url": f"https://example.test/{platform}/{slug}",
                    "slug": slug,
                    "main_file_attached": True,
                    "cover_confirmed": True,
                    "preview_confirmed": True,
                    "thumbnail_confirmed": True,
                    "tags_confirmed": True,
                    "image_count": 2,
                }
            )
            return base
        if platform == "etsy":
            base.update(
                {
                    "status": "draft",
                    "id": f"{platform}_{slug}",
                    "listing_id": f"{platform}_{slug}",
                    "url": f"https://example.test/{platform}/{slug}",
                    "file_attached": True,
                    "image_count": 2,
                    "tags_confirmed": True,
                    "materials_confirmed": True,
                    "category_confirmed": True,
                    "editor_audit": {"ok": True},
                }
            )
            return base
        if platform in {"kofi", "wordpress", "medium", "twitter", "printful"}:
            base.update(
                {
                    "status": "published",
                    "id": f"{platform}_{slug}",
                    "url": f"https://example.test/{platform}/{slug}",
                }
            )
            return base
        base.update({"status": "created", "id": f"{platform}_{slug}", "url": f"https://example.test/{platform}/{slug}"})
        return base

    async def get_analytics(self) -> dict:
        return {"platform": self.name, "sales": 0, "revenue": 0.0}

    async def update(self, listing_id: str, data: dict) -> dict:
        return {"platform": self.name, "status": "updated", "listing_id": listing_id}


@dataclass
class StaticScore:
    score10: int
    capabilities_count: int
    execute_lines: int
    branches: int
    calls: int
    async_methods: int


def _iter_agent_classes() -> list[type[BaseAgent]]:
    classes: list[type[BaseAgent]] = []
    for p in sorted((ROOT / "agents").glob("*.py")):
        if p.name in {"__init__.py", "base_agent.py", "agent_registry.py"}:
            continue
        mod = importlib.import_module(f"agents.{p.stem}")
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if obj is BaseAgent:
                continue
            if issubclass(obj, BaseAgent) and obj.__module__ == mod.__name__:
                classes.append(obj)
    uniq = {c.__name__: c for c in classes}
    return [uniq[k] for k in sorted(uniq.keys())]


def _static_score_for_class(cls: type[BaseAgent]) -> StaticScore:
    file_path = Path(inspect.getsourcefile(cls) or "")
    src = file_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    class_node = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls.__name__
    )
    exec_fn = next(
        (n for n in class_node.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "execute_task"),
        None,
    )
    caps_fn = next(
        (n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == "capabilities"),
        None,
    )
    caps = 0
    if caps_fn:
        for n in ast.walk(caps_fn):
            if isinstance(n, (ast.List, ast.Tuple)):
                caps = max(caps, len(n.elts))
    branches = sum(isinstance(n, (ast.If, ast.Match, ast.Try)) for n in ast.walk(exec_fn)) if exec_fn else 0
    calls = sum(isinstance(n, ast.Call) for n in ast.walk(exec_fn)) if exec_fn else 0
    lines = (exec_fn.end_lineno - exec_fn.lineno + 1) if exec_fn and exec_fn.end_lineno else 0
    async_methods = sum(isinstance(n, ast.AsyncFunctionDef) for n in class_node.body)

    score = 0
    score += 2 if caps >= 2 else (1 if caps == 1 else 0)
    score += 2 if lines >= 20 else (1 if lines >= 10 else 0)
    score += 2 if branches >= 3 else (1 if branches >= 1 else 0)
    score += 2 if calls >= 8 else (1 if calls >= 3 else 0)
    # Узкоспециализированные боевые агенты часто имеют 2-3 async метода.
    score += 2 if async_methods >= 5 else (1 if async_methods >= 2 else 0)
    return StaticScore(
        score10=score,
        capabilities_count=caps,
        execute_lines=lines,
        branches=branches,
        calls=calls,
        async_methods=async_methods,
    )


def _sample_kwargs(agent_name: str, capability: str) -> dict[str, Any]:
    base = {
        "step": "Mega test task",
        "goal_title": "Mega test goal",
        "content": "Test content",
        "topic": "AI productivity templates",
        "product": "AI Toolkit",
        "platform": "gumroad",
        "text": "hello world",
        "title": "Mega test title",
        "source_lang": "en",
        "target_lang": "de",
        "path": str(ROOT / "README.md"),
        "file_path": str(ROOT / "README.md"),
        "url": "https://example.com",
        "selector": "body",
        "fields": {"input[name='q']": "test"},
        "data": {
            "name": "Mega test product",
            "description": "Test",
            "price": 1,
            "pdf_path": str(ROOT / "README.md"),
            "preview_path": str(ROOT / "README.md"),
            "category": "Education",
            "tags": ["test"],
        },
    }
    if agent_name == "publisher_agent":
        base["platform"] = "wordpress"
    if agent_name == "smm_agent":
        base["platform"] = "twitter"
    if capability == "document_parse":
        base["path"] = str(ROOT / "AGENTS.md")
    return base


def _runtime_capabilities(agent_name: str, caps: list[str]) -> list[str]:
    if not caps:
        return []
    # Избегаем рекурсивной самодиспетчеризации в аудите; проверяем более безопасные боевые пути.
    skip = {
        "vito_core": {"orchestrate", "dispatch"},
    }
    filtered = [c for c in caps if c not in skip.get(agent_name, set())]
    return filtered or caps[:1]


def build_agents_for_audit() -> list[BaseAgent]:
    llm = DummyLLMRouter()
    memory = DummyMemory()
    finance = DummyFinance()
    deps = {"llm_router": llm, "memory": memory, "finance": finance, "comms": None}

    registry = AgentRegistry()
    browser = BrowserAgent(**deps)
    qj = QualityJudge(**deps)

    commerce = {
        "gumroad": DummyPlatform("gumroad"),
        "etsy": DummyPlatform("etsy"),
        "kofi": DummyPlatform("kofi"),
        "printful": DummyPlatform("printful"),
    }
    publish = {"wordpress": DummyPlatform("wordpress"), "medium": DummyPlatform("medium")}
    social = {"twitter": DummyPlatform("twitter")}

    agents: list[BaseAgent] = [
        VITOCore(registry=registry, skill_registry=None, **deps),
        TrendScout(browser_agent=browser, **deps),
        ContentCreator(quality_judge=qj, **deps),
        SMMAgent(platforms=social, **deps),
        MarketingAgent(**deps),
        ECommerceAgent(platforms=commerce, **deps),
        SEOAgent(**deps),
        EmailAgent(**deps),
        TranslationAgent(**deps),
        AnalyticsAgent(registry=registry, **deps),
        EconomicsAgent(**deps),
        LegalAgent(**deps),
        RiskAgent(**deps),
        SecurityAgent(**deps),
        DevOpsAgent(**deps),
        HRAgent(**deps),
        PartnershipAgent(**deps),
        ResearchAgent(**deps),
        DocumentAgent(**deps),
        AccountManager(**deps),
        browser,
        PublisherAgent(quality_judge=qj, platforms=publish, **deps),
        qj,
    ]
    for a in agents:
        registry.register(a)
    return agents


async def run_megatest() -> dict[str, Any]:
    classes = _iter_agent_classes()
    class_map = {c.__name__: c for c in classes}
    agents = build_agents_for_audit()
    by_name = {a.name: a for a in agents}

    rows: list[dict[str, Any]] = []
    try:
        for agent_name, agent in sorted(by_name.items()):
            cls = class_map.get(type(agent).__name__)
            static = _static_score_for_class(cls) if cls else StaticScore(0, 0, 0, 0, 0, 0)
            caps = list(agent.capabilities or [])
            runtime_caps = _runtime_capabilities(agent_name, caps)

            runtime_rows: list[dict[str, Any]] = []
            for cap in runtime_caps:
                kwargs = _sample_kwargs(agent_name, cap)
                try:
                    result = await asyncio.wait_for(agent.execute_task(cap, **kwargs), timeout=25)
                    ok_shape = isinstance(result, TaskResult)
                    err = str(getattr(result, "error", "") or "")
                    runtime_rows.append(
                        {
                            "capability": cap,
                            "task_success": bool(result.success) if ok_shape else False,
                            "result_shape_ok": ok_shape,
                            "error": err[:240],
                            "non_wrapper_path": not ("неизвестный task_type" in err.lower() or "unknown task_type" in err.lower()),
                        }
                    )
                except Exception as e:
                    runtime_rows.append(
                        {
                            "capability": cap,
                            "task_success": False,
                            "result_shape_ok": False,
                            "error": str(e)[:240],
                            "non_wrapper_path": False,
                        }
                    )

            runtime_ok = any(
                r["result_shape_ok"] and r["non_wrapper_path"] and r["task_success"]
                for r in runtime_rows
            )
            combat_ready = bool(static.score10 >= 6 and runtime_ok and len(caps) > 0)
            rows.append(
                {
                    "agent": agent_name,
                    "class": type(agent).__name__,
                    "capabilities": caps,
                    "runtime_capabilities_checked": runtime_caps,
                    "static": static.__dict__,
                    "runtime": runtime_rows,
                    "combat_ready": combat_ready,
                }
            )
    finally:
        async def _safe_stop(agent: BaseAgent) -> None:
            try:
                await asyncio.wait_for(agent.stop(), timeout=3)
            except Exception:
                pass

        await asyncio.gather(*[_safe_stop(agent) for agent in reversed(agents)], return_exceptions=True)

    total = len(rows)
    ready = sum(1 for r in rows if r["combat_ready"])
    score = round((ready / total) * 100.0, 2) if total else 0.0
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_agents": total,
        "combat_ready_agents": ready,
        "combat_readiness_percent": score,
        "rows": rows,
    }


def main() -> int:
    report = asyncio.run(run_megatest())
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    path = reports_dir / f"VITO_AGENT_MEGATEST_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
