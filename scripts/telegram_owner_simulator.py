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


async def _amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="smoke", help="smoke | platform_context")
    ap.add_argument("--out", default="", help="Optional output report path")
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
    comms = vito.comms
    owner_id = int(getattr(settings, "TELEGRAM_OWNER_CHAT_ID", 0) or 0)

    report: dict[str, Any] = {
        "timestamp": _utc_now(),
        "scenario": args.scenario,
        "mode": "local_owner_simulator",
        "steps": [],
        "summary": {"passed": 0, "failed": 0, "total": len(steps)},
    }

    try:
        for st in steps:
            replies = await _run_step(comms, owner_id, st.text)
            joined = "\n\n".join(replies).strip()
            ok, reasons = _check(joined, st.expect_any, st.reject_any)
            row = {
                "id": st.id,
                "input": st.text,
                "reply_text": joined,
                "pass": bool(joined and ok),
                "reasons": reasons if not (joined and ok) else [],
                "at": _utc_now(),
            }
            if not joined:
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
