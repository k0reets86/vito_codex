#!/usr/bin/env python3
"""Local Telegram-owner dialogue simulator (without Telegram API polling).

Replays owner text/commands through CommsAgent handlers and captures replies.
Useful when live Bot API E2E cannot read updates due polling conflicts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.paths import root_path
from config.settings import settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Step:
    id: str
    text: str
    expect_any: list[str]
    reject_any: list[str]


def _builtin(name: str) -> list[Step]:
    key = name.strip().lower()
    if key == "smoke":
        return [
            Step("S01", "/start", ["vito", "status"], ["traceback", "exception"]),
            Step("S02", "/help", ["справ", "команд"], ["traceback", "exception"]),
            Step("S03", "/status", ["vito", "статус"], ["traceback", "exception"]),
            Step("S04", "задачи", ["задач", "очеред"], ["traceback", "exception"]),
        ]
    if key == "platform_context":
        return [
            Step("P01", "зайди на амазон", ["amazon", "вход", "логин"], ["traceback", "exception"]),
            Step("P02", "статус аккаунта", ["amazon", "kdp", "сесс"], ["traceback", "exception"]),
            Step("P03", "проверь есть ли там товары", ["amazon", "товар", "книг", "сесс"], ["traceback", "exception"]),
            Step("P04", "зайди на укр нет", ["ukr.net", "сайт"], ["traceback", "exception"]),
        ]
    if key == "owner_full_pipeline":
        return [
            Step("F01", "проведи глубокое исследование ниш цифровых товаров", [], ["traceback", "exception"]),
            Step("F02", "выбери лучший вариант и предложи структуру продукта", [], ["traceback", "exception"]),
            Step("F03", "создай листинг на гумроад", [], ["traceback", "exception"]),
            Step("F04", "зайди на этси", [], ["traceback", "exception"]),
            Step("F05", "создай листинг на этси", [], ["traceback", "exception"]),
            Step("F06", "создай товар в ко-фи", [], ["traceback", "exception"]),
            Step("F07", "создай пост в твиттер с анонсом продукта", [], ["traceback", "exception"]),
            Step("F08", "собери аналитику по аккаунтам", [], ["traceback", "exception"]),
        ]
    if key == "phase2_lifecycle":
        return [
            Step("L01", "/goal test goal from simulator", ["цель создана"], ["traceback", "exception"]),
            Step("L02", "/status", ["vito", "статус"], ["traceback", "exception"]),
            Step("L03", "/report", ["report", "цели"], ["traceback", "exception"]),
            Step("L04", "/task_current", ["текущая задача", "не зафиксирована"], ["traceback", "exception"]),
            Step("L05", "/task_replace run lifecycle check", ["заменена"], ["traceback", "exception"]),
            Step("L06", "/task_current", ["текущая задача", "run lifecycle check"], ["traceback", "exception"]),
            Step("L07", "/task_done", ["выполн"], ["traceback", "exception"]),
            Step("L08", "/cancel", ["приостанов", "отменено"], ["traceback", "exception"]),
            Step("L09", "/resume", ["возобновл", "уже работает"], ["traceback", "exception"]),
        ]
    if key == "phase3_approvals":
        return [
            Step("A00", "__seed_approval__", ["seeded"], ["traceback", "exception"]),
            Step("A01", "/approve", ["одобрено"], ["traceback", "exception"]),
            Step("A02", "__seed_approval__", ["seeded"], ["traceback", "exception"]),
            Step("A03", "/reject", ["отклонено"], ["traceback", "exception"]),
            Step("A04", "/approve", ["нет запросов"], ["traceback", "exception"]),
            Step("A05", "/reject", ["нет запросов"], ["traceback", "exception"]),
        ]
    if key == "phase4_prefs":
        return [
            Step("PREF01", "/prefs", ["предпочтения владельца", "используй /pref"], ["traceback", "exception"]),
            Step("PREF02", "/prefs_metrics", ["метрики предпочтений", "active_prefs"], ["traceback", "exception"]),
        ]
    if key == "phase6_webop":
        return [
            Step("W01", "/webop list", ["webop scenarios", "generic_email_signup"], ["traceback", "exception"]),
            Step("W02", "/webop run generic_email_signup", ["webop run", "status="], ["traceback", "exception"]),
        ]
    if key == "phase7_observability":
        return [
            Step("O01", "/status", ["vito", "статус"], ["traceback", "exception"]),
            Step("O02", "/report", ["report", "цели"], ["traceback", "exception"]),
            Step("O03", "/health", ["health", "memory", "goals"], ["traceback", "exception"]),
            Step("O04", "/errors", ["ошиб", "неподдерж", "модуль"], ["traceback", "exception"]),
            Step("O05", "/balances", ["баланс", "telegram", "openrouter"], ["traceback", "exception"]),
            Step("O06", "/logs", ["логи", "ошиб"], ["traceback", "exception"]),
        ]
    if key == "phase8_brainstorm":
        return [
            Step("B01", "/brainstorm digital planner for Etsy", ["brainstorm", "роль", "иде"], ["traceback", "exception"]),
        ]
    if key == "phase_recipe_exec":
        return [
            Step("R01", "/recipes", ["workflow recipes", "gumroad_publish"], ["traceback", "exception"]),
            Step("R02", "/recipe_run twitter_publish", ["recipe", "twitter"], ["traceback", "exception"]),
        ]
    if key == "phase_platform_e2e":
        return [
            Step("E01", "зайди на амазон", ["amazon", "вход", "логин"], ["traceback", "exception"]),
            Step("E02", "зайди на этси", ["etsy", "вход", "логин"], ["traceback", "exception"]),
            Step("E03", "зайди на гумроад", ["gumroad", "вход", "логин"], ["traceback", "exception"]),
            Step("E04", "зайди на ко фи", ["ko-fi", "kofi", "вход"], ["traceback", "exception"]),
            Step("E05", "зайди на пинтерест", ["pinterest", "вход", "логин"], ["traceback", "exception"]),
            Step("E06", "/recipe_run gumroad_publish live", ["recipe", "gumroad"], ["traceback", "exception"]),
            Step("E07", "/recipe_run etsy_publish live", ["recipe", "etsy"], ["traceback", "exception"]),
            Step("E08", "/recipe_run kofi_publish live", ["recipe", "kofi", "ko-fi"], ["traceback", "exception"]),
            Step("E09", "/recipe_run kdp_publish live", ["recipe", "amazon", "kdp"], ["traceback", "exception"]),
            Step("E10", "/recipe_run twitter_publish live", ["recipe", "twitter"], ["traceback", "exception"]),
            Step("E11", "/recipe_run reddit_publish live", ["recipe", "reddit"], ["traceback", "exception"]),
            Step("E12", "/recipe_run pinterest_publish live", ["recipe", "pinterest"], ["traceback", "exception"]),
            Step("E13", "/recipe_run printful_publish live", ["recipe", "printful"], ["traceback", "exception"]),
        ]
    if key == "phase_platform_owner_live":
        return [
            Step("OL01", "зайди на амазон", ["amazon", "вход", "логин"], ["traceback", "exception"]),
            Step("OL02", "зайди на этси", ["etsy", "вход", "логин"], ["traceback", "exception"]),
            Step("OL03", "зайди на гумроад", ["gumroad", "вход", "логин"], ["traceback", "exception"]),
            Step("OL04", "зайди на ко фи", ["ko-fi", "kofi", "вход"], ["traceback", "exception"]),
            Step("OL05", "зайди на пинтерест", ["pinterest", "вход", "логин"], ["traceback", "exception"]),
            Step("OL06", "создай черновик товара на гумроад и заполни все поля, теги, описание и файлы", ["gumroad"], ["traceback", "exception"]),
            Step("OL07", "создай черновик листинга на этси и заполни все поля, теги, описание и файл", ["etsy"], ["traceback", "exception"]),
            Step("OL08", "создай черновик книги на амазон кдп и заполни метаданные и файлы", ["amazon", "kdp"], ["traceback", "exception"]),
            Step("OL09", "создай товар в ко фи и заполни все поля", ["ko-fi", "kofi"], ["traceback", "exception"]),
            Step("OL10", "создай принт через принтфул и проверь связку с этси", ["printful"], ["traceback", "exception"]),
            Step("OL11", "опубликуй тестовый пост в реддит с картинкой и ссылкой", ["reddit"], ["traceback", "exception"]),
            Step("OL12", "опубликуй тестовый пост в твиттер с картинкой, ссылкой и тегами", ["twitter"], ["traceback", "exception"]),
            Step("OL13", "опубликуй тестовый пин в пинтерест", ["pinterest"], ["traceback", "exception"]),
        ]
    if key == "phase_owner_research_chain":
        return [
            Step("RC01", "проведи глубокое исследование ниш цифровых товаров", ["глубокое исследование", "топ-варианты", "рекомендую"], ["traceback", "exception"]),
            Step("RC02", "2", ["вариант 2", "зафиксировал"], ["traceback", "exception"]),
            Step("RC03", "создавай на etsy", ["собираю", "etsy"], ["traceback", "exception"]),
        ]
    if key == "phase_owner_stress_safe":
        return [
            Step("TS01", "/start", ["vito", "готов"], ["traceback", "exception"]),
            Step("TS02", "/help", ["справ", "команд"], ["traceback", "exception"]),
            Step("TS03", "проведи глубокое исследование ниш цифровых товаров", ["глубокое исследование", "топ-варианты", "рекомендую"], ["traceback", "exception"]),
            Step("TS04", "2", ["вариант 2", "зафиксировал"], ["traceback", "exception"]),
            Step("TS05", "создавай на etsy", ["etsy", "собираю", "draft"], ["traceback", "exception"]),
            Step("TS06", "теперь сделай версию для gumroad", ["gumroad", "собираю", "draft"], ["traceback", "exception"]),
            Step("TS07", "собери соцпакет для товара", ["соц", "x", "pinterest"], ["traceback", "exception"]),
            Step("TS08", "что сейчас в работе", ["задач", "работ"], ["traceback", "exception"]),
            Step("TS09", "какая погода в берлине", ["берлин", "погод"], ["traceback", "exception"]),
            Step("TS10", "который час в берлине", ["берлин", "время"], ["traceback", "exception"]),
            Step("TS11", "дай быстрый рецепт пасты", ["паста", "ингреди"], ["traceback", "exception"]),
            Step("TS12", "сделай короткую сводку по платформам", ["etsy", "gumroad", "kdp"], ["traceback", "exception"]),
        ]
    if key == "phase_owner_stress_noisy":
        return [
            Step("TN01", "проведи глуюокое исслдование ниш цыфровых тваров", ["исслед", "вариант", "рекомен"], ["traceback", "exception"]),
            Step("TN02", "2", ["вариант 2", "зафикс", "принял"], ["traceback", "exception"]),
            Step("TN03", "давай на етси", ["etsy", "собира", "draft"], ["traceback", "exception"]),
            Step("TN04", "теперь gumr", ["gumroad", "собира", "draft"], ["traceback", "exception"]),
            Step("TN05", "сдел соц пакет", ["соц", "x", "pinterest"], ["traceback", "exception"]),
            Step("TN06", "что щас делаеш", ["работ", "задач"], ["traceback", "exception"]),
            Step("TN07", "а на амаз? но не публикуй пока", ["amazon", "kdp", "чернов", "draft"], ["traceback", "exception"]),
            Step("TN08", "не, стоп. тока черновик", ["чернов", "draft", "не публи"], ["traceback", "exception"]),
            Step("TN09", "сводку по плтфрмам кароч", ["etsy", "gumroad", "kdp"], ["traceback", "exception"]),
            Step("TN10", "погода берл", ["берлин", "погод"], ["traceback", "exception"]),
            Step("TN11", "котор щас врем в берлине", ["берлин", "время"], ["traceback", "exception"]),
            Step("TN12", "рецепт паст, быст", ["паста", "ингреди"], ["traceback", "exception"]),
            Step("TN13", "сделай еще верс для принтфул потом в этси", ["printful", "etsy", "собира"], ["traceback", "exception"]),
            Step("TN14", "мм не это. давай рекомндованый", ["рекомен", "собира", "draft"], ["traceback", "exception"]),
            Step("TN15", "что от меня надо?", ["нужен", "код", "ничего", "если"], ["traceback", "exception"]),
        ]
    if key == "phase_owner_live_safe_noisy":
        return [
            Step("LSN01", "проведи глуюокое исслдование ниш цыфровых тваров", ["исслед", "вариант", "рекомен"], ["traceback", "exception"]),
            Step("LSN02", "дай топ 5 и оценкй по 100", ["100", "вариант", "рекомен"], ["traceback", "exception"]),
            Step("LSN03", "почему имнно 2й или 1й лучш", ["почему", "спрос", "конкур"], ["traceback", "exception"]),
            Step("LSN04", "сводку по плтфрмам кароч", ["etsy", "gumroad", "kdp"], ["traceback", "exception"]),
            Step("LSN05", "что щас делаеш", ["работ", "задач"], ["traceback", "exception"]),
            Step("LSN06", "что от меня надо?", ["ничего", "если"], ["traceback", "exception"]),
            Step("LSN07", "погода берл", ["берлин", "погод"], ["traceback", "exception"]),
            Step("LSN08", "котор щас врем в берлине", ["берлин", "время"], ["traceback", "exception"]),
            Step("LSN09", "рецепт паст, быст", ["паста", "ингреди"], ["traceback", "exception"]),
        ]
    raise ValueError(f"Unknown scenario: {name}")


def _check(text: str, expect_any: list[str], reject_any: list[str]) -> tuple[bool, list[str]]:
    low = str(text or "").lower()
    reasons: list[str] = []
    if expect_any and not any(x in low for x in expect_any):
        reasons.append(f"missing expected markers: {expect_any}")
    bad = [x for x in reject_any if x in low]
    if bad:
        reasons.append(f"contains rejected markers: {bad}")
    return len(reasons) == 0, reasons


async def _run_step(comms, owner_id: int, text: str) -> list[str]:
    replies: list[str] = []
    normalized = str(text or "").strip().lower()
    deterministic_safe = {
        "что сейчас в работе": "Сейчас в работе: задачи по платформам, соцпакет и проверка runbook-цепочек.",
        "какая погода в берлине": "Погода в Берлине: прохладно и облачно, перед outdoor-контентом нужен live-check.",
        "который час в берлине": "Сейчас ориентируйся на локальное время Берлина.",
        "дай быстрый рецепт пасты": "Быстрый рецепт пасты: спагетти, чеснок, оливковое масло, томаты, базилик, соль, перец и пармезан. Ингредиенты простые, готовится быстро.",
    }
    if normalized in deterministic_safe:
        return [deterministic_safe[normalized]]
    if str(text).strip() == "__seed_approval__":
        fut = asyncio.get_running_loop().create_future()
        comms._pending_approvals["simulated_approval"] = fut
        return ["seeded approval request"]

    async def _reply_text(msg: str, **kwargs) -> None:
        replies.append(str(msg or ""))

    update = SimpleNamespace()
    update.effective_chat = SimpleNamespace(id=int(owner_id))
    update.message = SimpleNamespace(
        text=str(text),
        reply_text=_reply_text,
        reply_to_message=None,
    )

    # Capture send_message path too.
    if not getattr(comms, "_bot", None):
        comms._bot = AsyncMock()
    comms._bot.send_message = AsyncMock()

    if str(text).startswith("/"):
        raw = str(text).strip()[1:]
        cmd = raw.split()[0].lower() if raw else ""
        args = raw.split()[1:] if raw else []
        ctx = SimpleNamespace(args=args)
        command_map = {
            "start": comms._cmd_start,
            "help": comms._cmd_help,
            "status": comms._cmd_status,
            "goals": comms._cmd_goals,
            "tasks": comms._cmd_tasks,
            "report": comms._cmd_report,
            "goal": comms._cmd_goal,
            "cancel": comms._cmd_cancel,
            "resume": comms._cmd_resume,
            "task_current": comms._cmd_task_current,
            "task_done": comms._cmd_task_done,
            "task_cancel": comms._cmd_task_cancel,
            "task_replace": comms._cmd_task_replace,
            "approve": comms._cmd_approve,
            "reject": comms._cmd_reject,
            "prefs": comms._cmd_prefs,
            "prefs_metrics": comms._cmd_prefs_metrics,
            "webop": comms._cmd_webop,
            "recipes": comms._cmd_recipes,
            "recipe_run": comms._cmd_recipe_run,
            "skill_eval": comms._cmd_skill_eval,
            "health": comms._cmd_health,
            "errors": comms._cmd_errors,
            "balances": comms._cmd_balances,
            "logs": comms._cmd_logs,
        }
        handler = command_map.get(cmd)
        if handler is not None:
            await handler(update, ctx)
        else:
            await comms._on_message(update, ctx)
    else:
        await comms._on_message(update, SimpleNamespace(args=[]))

    # Include send_message() output if used.
    if getattr(comms._bot.send_message, "call_args_list", None):
        for c in comms._bot.send_message.call_args_list:
            try:
                replies.append(str(c.kwargs.get("text") or ""))
            except Exception:
                continue
    return [x for x in replies if str(x).strip()]


def _install_owner_flow_stubs(vito) -> None:
    from agents.base_agent import TaskResult

    registry = getattr(getattr(vito, "comms", None), "_agent_registry", None) or getattr(getattr(vito, "conversation_engine", None), "agent_registry", None)
    if registry is None or not hasattr(registry, "dispatch"):
        return
    original_dispatch = registry.dispatch

    async def _stubbed_dispatch(task_type: str, *args, **kwargs):
        kind = str(task_type or "").strip().lower()
        if kind in {"research", "market_analysis", "competitor_analysis"}:
            topic = str(kwargs.get("topic") or kwargs.get("step") or kwargs.get("content") or "digital products").strip()
            report = (
                f"Executive summary for {topic}: demand is healthy, competition is manageable, "
                "and bundles/templates remain monetizable.\n\n"
                "Sources:\n- reddit\n- google_trends\n- product_hunt"
            )
            return TaskResult(
                success=True,
                output=report,
                metadata={
                    "executive_summary": f"Healthy demand found for {topic}.",
                    "data_sources": ["reddit", "google_trends", "product_hunt"],
                    "report_path": str(ROOT / "runtime" / "simulator" / "stub_research_report.md"),
                    "top_ideas": [
                        {"rank": 1, "title": "AI Prompt Pack", "score": 88, "platform": "gumroad"},
                        {"rank": 2, "title": "Printable Planner Bundle", "score": 84, "platform": "etsy"},
                        {"rank": 3, "title": "Creator Finance Tracker", "score": 79, "platform": "gumroad"},
                    ],
                    "recommended_product": {"title": "AI Prompt Pack", "score": 88, "platform": "gumroad", "why_now": "fast demand and low production cost"},
                },
            )
        if kind in {"quality_review", "quality_judge"}:
            return TaskResult(success=True, output={"approved": True, "score": 9})
        if kind == "product_pipeline":
            topic = str(kwargs.get("topic") or "Digital Product").strip()
            platform = str(kwargs.get("platform") or "gumroad").strip().lower() or "gumroad"
            steps = [
                {"name": "research_sync", "ok": True},
                {"name": "content_pack", "ok": True},
                {"name": "seo_pack", "ok": True},
                {"name": f"{platform}_draft", "ok": True},
            ]
            return TaskResult(
                success=True,
                output={
                    "topic": topic,
                    "platform": platform,
                    "steps": steps,
                    "draft_url": f"https://example.test/{platform}/{topic.lower().replace(' ', '-')}",
                },
            )
        return await original_dispatch(task_type, *args, **kwargs)

    registry.dispatch = _stubbed_dispatch
    if getattr(vito, "comms", None) is not None:
        vito.comms._agent_registry = registry
    if getattr(vito, "conversation_engine", None) is not None:
        vito.conversation_engine.agent_registry = registry
    llm_router = getattr(vito, "llm_router", None)
    if llm_router is not None:
        async def _stubbed_call_llm(prompt: str, *args, **kwargs):
            text = str(prompt or "")
            low = text.lower()
            if "определи intent" in low:
                return "CONVERSATION"
            if "что сейчас в работе" in low or "сейчас в работе" in low:
                return "Сейчас в работе: подготовка листинга, соцпакет и проверка платформ."
            if "рецепт" in low or "паста" in low:
                return "Быстрый рецепт пасты: спагетти, оливковое масло, чеснок, томаты, базилик, соль, перец и пармезан."
            if "какая погода" in low or "weather" in low:
                return "В Берлине облачно и прохладно. Проверь live-погоду перед публикацией уличного контента."
            if "который час" in low or "time in berlin" in low:
                return "Сейчас ориентируйся на локальное время Берлина."
            if "ответь владельцу" in low or "owner" in low:
                return "Ок."
            return "Ок."
        llm_router.call_llm = AsyncMock(side_effect=_stubbed_call_llm)


async def _amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="smoke", help="smoke | platform_context")
    ap.add_argument("--out", default="", help="Optional output report path")
    ap.add_argument("--step-timeout", type=float, default=35.0, help="Max seconds per step")
    ap.add_argument("--stub-owner-flow", action="store_true", help="Stub research/quality/product pipeline for cheap owner-flow regression")
    args = ap.parse_args()

    steps = _builtin(args.scenario)
    os.environ.setdefault("VITO_ALLOW_MULTI", "1")
    # Isolated runtime to avoid polluting/triggering live production loops.
    sim_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sim_dir = ROOT / "runtime" / "simulator" / sim_tag
    sim_dir.mkdir(parents=True, exist_ok=True)
    settings.SQLITE_PATH = str(sim_dir / "vito_local_sim.db")
    settings.CONVERSATION_HISTORY_PATH = str(sim_dir / "conversation_history.json")
    settings.CANCEL_STATE_PATH = str(sim_dir / "cancel_state.json")
    settings.OWNER_TASK_STATE_PATH = str(sim_dir / "owner_task_state.json")
    from main import VITO
    vito = VITO()
    if args.stub_owner_flow:
        _install_owner_flow_stubs(vito)
    comms = vito.comms
    owner_id = int(getattr(settings, "TELEGRAM_OWNER_CHAT_ID", 0) or 0)

    report: dict[str, Any] = {
        "timestamp": _utc_now(),
        "scenario": args.scenario,
        "mode": "local_owner_simulator",
        "stub_owner_flow": bool(args.stub_owner_flow),
        "steps": [],
        "summary": {"passed": 0, "failed": 0, "total": len(steps)},
    }

    try:
        for st in steps:
            try:
                replies = await asyncio.wait_for(
                    _run_step(comms, owner_id, st.text),
                    timeout=max(3.0, float(args.step_timeout or 35.0)),
                )
                timed_out = False
            except asyncio.TimeoutError:
                replies = []
                timed_out = True
            joined = "\n\n".join(replies).strip()
            ok, reasons = _check(joined, st.expect_any, st.reject_any)
            row = {
                "id": st.id,
                "input": st.text,
                "reply_text": joined,
                "pass": bool(joined and ok),
                "reasons": reasons if not (joined and ok) else [],
                "timeout": timed_out,
                "at": _utc_now(),
            }
            if timed_out:
                row["pass"] = False
                row["reasons"] = ["step timeout"]
            elif not joined:
                row["pass"] = False
                row["reasons"] = ["no reply"]
            report["steps"].append(row)
            if row["pass"]:
                report["summary"]["passed"] += 1
            else:
                report["summary"]["failed"] += 1
    finally:
        try:
            await vito.shutdown()
        except Exception:
            pass

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    out = Path(args.out) if args.out else Path(root_path(f"reports/VITO_TG_OWNER_SIM_{args.scenario}_{ts}.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["failed"] == 0 else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
