from __future__ import annotations

import json

from telegram import Update
from telegram.ext import ContextTypes

from config.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


async def cmd_spend(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    spend = float(agent._llm_router.get_daily_spend() if agent._llm_router else 0.0)
    fin_spend = float(agent._finance.get_daily_spent() if agent._finance else 0.0)
    limit = settings.DAILY_LIMIT_USD
    lines = [
        f"Расходы сегодня (LLM): ${spend:.2f} / ${limit:.2f}",
        f"Осталось по лимиту LLM: ${max(limit - spend, 0):.2f}",
    ]
    if fin_spend > 0:
        lines.append(f"Финконтроль (все типы расходов): ${fin_spend:.2f}")
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    logger.info("Команда /spend выполнена", extra={"event": "cmd_spend"})


async def cmd_approve(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._pending_approvals:
        await update.message.reply_text("Нет запросов, ожидающих одобрения.", reply_markup=agent._main_keyboard())
        return
    request_id = next(iter(agent._pending_approvals))
    future = agent._pending_approvals.pop(request_id)
    if not future.done():
        future.set_result(True)
    await update.message.reply_text("Одобрено.", reply_markup=agent._main_keyboard())
    logger.info(
        f"Запрос одобрен: {request_id}",
        extra={"event": "approval_granted", "context": {"request_id": request_id}},
    )


async def cmd_reject(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._pending_approvals:
        await update.message.reply_text("Нет запросов, ожидающих одобрения.", reply_markup=agent._main_keyboard())
        return
    request_id = next(iter(agent._pending_approvals))
    future = agent._pending_approvals.pop(request_id)
    if not future.done():
        future.set_result(False)
    await update.message.reply_text("Отклонено.", reply_markup=agent._main_keyboard())
    logger.info(
        f"Запрос отклонён: {request_id}",
        extra={"event": "approval_rejected", "context": {"request_id": request_id}},
    )


async def cmd_recipes(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    try:
        from modules.workflow_recipes import list_workflow_recipes, get_workflow_recipe
        args = list(getattr(context, "args", None) or [])
        if args:
            key = str(args[0] or "").strip().lower()
            rec = get_workflow_recipe(key)
            if not rec:
                await update.message.reply_text(f"Recipe не найден: {key}", reply_markup=agent._main_keyboard())
                return
            lines = [
                f"Recipe: {key}",
                f"Platform: {rec.get('platform', '-')}",
                f"Goal: {rec.get('goal', '-')}",
                "Steps:",
            ]
            for idx, step in enumerate(rec.get("steps", []), start=1):
                lines.append(f"{idx}. {step}")
            lines.append(f"Evidence: {', '.join(rec.get('required_evidence', []) or [])}")
            await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
            return
        rows = list_workflow_recipes()
        lines = ["Workflow Recipes:"]
        for r in rows:
            lines.append(f"- {r.get('name')}: {r.get('platform')} ({len(r.get('steps', []) or [])} steps)")
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Recipes error: {e}", reply_markup=agent._main_keyboard())


async def cmd_workflow(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    try:
        from modules.workflow_state_machine import WorkflowStateMachine
        wf = WorkflowStateMachine()
        health = wf.health()
        goal_id = " ".join(context.args).strip() if getattr(context, "args", None) else ""
        if not goal_id and agent._goal_engine:
            goals = agent._goal_engine.get_all_goals()
            if goals:
                goal_id = goals[-1].goal_id
        lines = [
            "Workflow",
            f"Всего: {health.get('workflows_total', 0)}",
            f"Обновлён: {health.get('last_update', '-')}",
        ]
        if goal_id:
            lines.append(f"Goal: {goal_id}")
            events = wf.recent_events(goal_id, limit=8)
            if events:
                for e in events:
                    lines.append(
                        f"- {e.get('created_at','')} | {e.get('from_state','')} -> {e.get('to_state','')} | {e.get('reason','')}"
                    )
            else:
                lines.append("- Нет событий по этой цели")
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Workflow error: {e}", reply_markup=agent._main_keyboard())


async def cmd_handoffs(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    try:
        from modules.data_lake import DataLake
        dl = DataLake()
        summary = dl.handoff_summary(days=7)[:10]
        recent = dl.recent_handoffs(limit=8)
        lines = ["Handoffs (7d)"]
        if summary:
            for r in summary:
                lines.append(
                    f"- {r.get('from','?')} -> {r.get('to','?')}: ok={r.get('ok',0)} fail={r.get('fail',0)} total={r.get('total',0)}"
                )
        else:
            lines.append("- Нет handoff событий")
        lines.append("")
        lines.append("Recent:")
        if recent:
            for r in recent[:5]:
                lines.append(
                    f"- {r.get('created_at','')} | {r.get('from','?')} -> {r.get('to','?')} | {r.get('status','?')} | {r.get('capability','')}"
                )
        else:
            lines.append("- Нет recent событий")
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Handoffs error: {e}", reply_markup=agent._main_keyboard())


async def send_prefs(agent, reply_to: Update | None = None) -> None:
    try:
        from modules.owner_model import OwnerPreferenceModel
        model = OwnerPreferenceModel()
        prefs = model.list_preferences(limit=20)
        if not prefs:
            msg = "Предпочтения владельца: пока нет записей. Используй /pref ключ=значение."
        else:
            lines = ["Предпочтения владельца:"]
            for p in prefs:
                conf = float(p.get("confidence", 0.0))
                key = p.get("pref_key", "")
                val = p.get("value")
                lines.append(f"- {key}: {val} (conf={conf:.2f})")
            lines.append("Чтобы добавить: /pref ключ=значение")
            msg = "\n".join(lines)
        if reply_to is not None and getattr(reply_to, "message", None):
            await reply_to.message.reply_text(msg, reply_markup=agent._main_keyboard())
        else:
            await agent.send_message(msg)
    except Exception:
        if reply_to is not None and getattr(reply_to, "message", None):
            await reply_to.message.reply_text("Не удалось загрузить предпочтения.", reply_markup=agent._main_keyboard())
        else:
            await agent.send_message("Не удалось загрузить предпочтения.")


async def send_prefs_metrics(agent, reply_to: Update | None = None) -> None:
    try:
        from modules.owner_pref_metrics import OwnerPreferenceMetrics
        metrics = OwnerPreferenceMetrics().summary()
        lines = ["Метрики предпочтений:"]
        for k, v in metrics.items():
            lines.append(f"- {k}: {v}")
        msg = "\n".join(lines)
        if reply_to is not None and getattr(reply_to, "message", None):
            await reply_to.message.reply_text(msg, reply_markup=agent._main_keyboard())
        else:
            await agent.send_message(msg)
    except Exception:
        if reply_to is not None and getattr(reply_to, "message", None):
            await reply_to.message.reply_text("Не удалось загрузить метрики предпочтений.", reply_markup=agent._main_keyboard())
        else:
            await agent.send_message("Не удалось загрузить метрики предпочтений.")


async def send_packs(agent, reply_to: Update | None = None) -> None:
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "capability_packs"
        packs = []
        for spec in root.glob("*/spec.json"):
            try:
                data = json.loads(spec.read_text(encoding="utf-8"))
            except Exception:
                continue
            packs.append((data.get("name") or spec.parent.name, data.get("category", ""), data.get("acceptance_status", "pending")))
        if not packs:
            msg = "Capability packs: пусто."
        else:
            lines = ["Capability packs:"]
            for name, cat, status in sorted(packs):
                lines.append(f"- {name} ({cat}) [{status}]")
            msg = "\n".join(lines)
        if reply_to is not None and getattr(reply_to, "message", None):
            await reply_to.message.reply_text(msg, reply_markup=agent._main_keyboard())
        else:
            await agent.send_message(msg)
    except Exception:
        if reply_to is not None and getattr(reply_to, "message", None):
            await reply_to.message.reply_text("Не удалось загрузить capability packs.", reply_markup=agent._main_keyboard())
        else:
            await agent.send_message("Не удалось загрузить capability packs.")


async def cmd_pubq(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._publisher_queue:
        await update.message.reply_text("PublisherQueue не подключён.", reply_markup=agent._main_keyboard())
        return
    try:
        st = agent._publisher_queue.stats()
        rows = agent._publisher_queue.list_jobs(limit=10)
        lines = [
            "Publish Queue",
            f"queued={st.get('queued',0)} running={st.get('running',0)} done={st.get('done',0)} failed={st.get('failed',0)} total={st.get('total',0)}",
        ]
        for r in rows[:8]:
            lines.append(
                f"- #{r.get('id')} {r.get('platform')} [{r.get('status')}] a={r.get('attempts',0)}/{r.get('max_attempts',0)}"
            )
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"PubQ error: {e}", reply_markup=agent._main_keyboard())


async def cmd_pubrun(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._publisher_queue:
        await update.message.reply_text("PublisherQueue не подключён.", reply_markup=agent._main_keyboard())
        return
    limit = 5
    try:
        if context.args:
            limit = max(1, min(20, int(context.args[0])))
    except Exception:
        limit = 5
    try:
        rows = await agent._publisher_queue.process_all(limit=limit)
        if not rows:
            await update.message.reply_text("Очередь пустая.", reply_markup=agent._main_keyboard())
            return
        ok = sum(1 for x in rows if x.get("status") == "done")
        fail = len(rows) - ok
        await update.message.reply_text(
            f"Publish run: processed={len(rows)} done={ok} fail/retry={fail}",
            reply_markup=agent._main_keyboard(),
        )
    except Exception as e:
        await update.message.reply_text(f"PubRun error: {e}", reply_markup=agent._main_keyboard())


async def cmd_webop(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._agent_registry:
        await update.message.reply_text("AgentRegistry не подключён.", reply_markup=agent._main_keyboard())
        return
    try:
        from modules.web_operator_pack import WebOperatorPack
        pack = WebOperatorPack(agent._agent_registry)
        args = context.args or []
        if not args or args[0] in {"list", "ls"}:
            items = pack.list_scenarios()
            text = "WebOp scenarios:\n" + ("\n".join(f"- {x}" for x in items) if items else "- empty")
            await update.message.reply_text(text, reply_markup=agent._main_keyboard())
            return
        if args[0] == "run":
            if len(args) < 2:
                await update.message.reply_text("Usage: /webop run <scenario_name>", reply_markup=agent._main_keyboard())
                return
            scenario = args[1]
            res = await pack.run(scenario, overrides={})
            await update.message.reply_text(
                f"WebOp run: {scenario}\nstatus={res.get('status')}\nerror={res.get('error','')}",
                reply_markup=agent._main_keyboard(),
            )
            return
        await update.message.reply_text("Usage: /webop list | /webop run <scenario>", reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"WebOp error: {e}", reply_markup=agent._main_keyboard())


async def cmd_clear_goals(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._goal_engine:
        await update.message.reply_text("GoalEngine не подключён.", reply_markup=agent._main_keyboard())
        return
    if not agent._is_confirmed(getattr(context, "args", None)):
        await update.message.reply_text(
            "Подтверди удаление всех целей: `/clear_goals yes`",
            reply_markup=agent._main_keyboard(),
        )
        return
    removed = agent._goal_engine.clear_all_goals()
    await update.message.reply_text(
        f"Очередь целей очищена. Удалено: {removed}.",
        reply_markup=agent._main_keyboard(),
    )


async def cmd_nettest(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    try:
        from modules.network_utils import basic_net_report
        report = basic_net_report()
        lines = ["VITO NetTest"]
        if report.get("seccomp"):
            lines.append(f"seccomp: {report['seccomp']}")
        for host, ok in report.get("dns", {}).items():
            lines.append(f"{host}: {'OK' if ok else 'FAIL'}")
        lines.append(f"overall: {'OK' if report.get('ok') else 'FAIL'}")
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"NetTest error: {e}", reply_markup=agent._main_keyboard())


async def cmd_smoke(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    try:
        from modules.platform_smoke import PlatformSmoke
        platforms = getattr(agent._decision_loop, "_platforms", {}) if agent._decision_loop else {}
        sm = PlatformSmoke(platforms)
        rows = await sm.run(names=["gumroad", "etsy", "kofi", "printful"])
        ok = sum(1 for r in rows if r.get("status") == "success")
        fail = len(rows) - ok
        lines = [f"Smoke: ok={ok}, fail={fail}"]
        for r in rows:
            lines.append(f"- {r.get('platform')}: {r.get('status')} ({r.get('detail','')})")
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Smoke error: {e}", reply_markup=agent._main_keyboard())
