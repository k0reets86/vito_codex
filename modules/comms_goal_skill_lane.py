from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from config.logger import get_logger

logger = get_logger(__name__)


async def cmd_goals(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._goal_engine:
        await update.message.reply_text("GoalEngine не подключён", reply_markup=agent._main_keyboard())
        return

    try:
        agent._goal_engine.reload_goals()
    except Exception:
        pass
    goals = agent._goal_engine.get_all_goals()
    if not goals:
        await update.message.reply_text("Нет целей.", reply_markup=agent._main_keyboard())
        return

    lines = []
    for g in goals[:15]:
        icon = {"completed": "done", "failed": "fail", "executing": ">>",
                "pending": "..", "waiting_approval": "??", "planning": "~~"}.get(
            g.status.value, g.status.value
        )
        lines.append(f"[{icon}] {g.title} (${g.estimated_cost_usd:.2f})")

    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    logger.info("Команда /goals выполнена", extra={"event": "cmd_goals"})


async def cmd_goals_all(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._goal_engine:
        await update.message.reply_text("GoalEngine не подключён", reply_markup=agent._main_keyboard())
        return
    try:
        agent._goal_engine.reload_goals()
    except Exception:
        pass
    goals = agent._goal_engine.get_all_goals(status=None)
    if not goals:
        await update.message.reply_text("Целей нет.", reply_markup=agent._main_keyboard())
        return
    lines = [f"Всего целей: {len(goals)}"]
    for g in goals[:30]:
        lines.append(f"[{g.status.value}] {g.title} (${g.estimated_cost_usd:.2f})")
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())


async def cmd_goal(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._goal_engine:
        await update.message.reply_text("GoalEngine не подключён", reply_markup=agent._main_keyboard())
        return

    text = update.message.text.removeprefix("/goal").strip()
    if not text:
        await update.message.reply_text("Использование: /goal <описание цели>", reply_markup=agent._main_keyboard())
        return

    from goal_engine import GoalPriority

    goal = agent._goal_engine.create_goal(
        title=text[:100],
        description=text,
        priority=GoalPriority.HIGH,
        source="owner",
    )
    if agent._owner_task_state:
        try:
            agent._owner_task_state.set_active(text, source="telegram", intent="goal_request", force=False)
        except Exception:
            pass
    await update.message.reply_text(
        f"Цель создана: {goal.title}\nПриоритет: HIGH.",
        reply_markup=agent._main_keyboard(),
    )
    logger.info(
        f"Цель от владельца: {goal.goal_id}",
        extra={"event": "owner_goal", "context": {"goal_id": goal.goal_id, "title": text[:100]}},
    )


async def cmd_agents(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._agent_registry:
        await update.message.reply_text("AgentRegistry не подключён", reply_markup=agent._main_keyboard())
        return

    statuses = agent._agent_registry.get_all_statuses()
    if not statuses:
        await update.message.reply_text("Нет зарегистрированных агентов.", reply_markup=agent._main_keyboard())
        return

    lines = [f"Агенты ({len(statuses)}):"]
    for s in statuses:
        icon = {"idle": "o", "running": ">>", "stopped": "x", "error": "!"}.get(s["status"], "?")
        lines.append(f"[{icon}] {s['name']} — {s['status']} (done:{s.get('tasks_completed', 0)}, ${s.get('total_cost', 0):.2f})")

    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    logger.info("Команда /agents выполнена", extra={"event": "cmd_agents"})


async def cmd_skill_matrix_v2(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._agent_registry:
        await update.message.reply_text("AgentRegistry не подключён", reply_markup=agent._main_keyboard())
        return
    try:
        rows = agent._agent_registry.get_skill_matrix_v2()
    except Exception as e:
        await update.message.reply_text(f"Ошибка Skill Matrix v2: {e}", reply_markup=agent._main_keyboard())
        return
    if not rows:
        await update.message.reply_text("Skill Matrix v2 пуст.", reply_markup=agent._main_keyboard())
        return
    lines = [f"Skill Matrix v2: {len(rows)} агентов"]
    for r in rows:
        lines.append(
            f"- {r.get('agent')}: kind={r.get('primary_kind')} "
            f"svc={len(r.get('service', []))} helper={len(r.get('helper', []))} recipe={len(r.get('recipe', []))}"
        )
    await update.message.reply_text("\n".join(lines[:60]), reply_markup=agent._main_keyboard())


async def cmd_skill_eval(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    args = list(getattr(context, "args", None) or [])
    if len(args) < 2:
        await update.message.reply_text(
            "Использование: /skill_eval <candidate_desc> | <baseline_desc>",
            reply_markup=agent._main_keyboard(),
        )
        return
    raw = " ".join(args)
    if "|" not in raw:
        await update.message.reply_text(
            "Формат: /skill_eval candidate | baseline",
            reply_markup=agent._main_keyboard(),
        )
        return
    candidate_desc, baseline_desc = [x.strip() for x in raw.split("|", 1)]
    from modules.skill_eval_loop import EvalCase, run_skill_eval_loop
    evals = [
        EvalCase(id="1", prompt="проведи глубокое исследование ниши", should_trigger=True, required_terms=["исслед"], forbidden_terms=[]),
        EvalCase(id="2", prompt="опубликуй листинг на gumroad", should_trigger=True, required_terms=["gumroad"], forbidden_terms=[]),
        EvalCase(id="3", prompt="какая погода в берлине", should_trigger=False, required_terms=[], forbidden_terms=["погода"]),
        EvalCase(id="4", prompt="просто поболтай со мной", should_trigger=False, required_terms=[], forbidden_terms=["поболтай"]),
    ]
    res = run_skill_eval_loop(candidate_desc, baseline_desc, evals, max_iters=3)
    rate = float(res.get("best_pass_rate", 0.0))
    iters = int(res.get("iterations", 0))
    await update.message.reply_text(
        f"Skill Eval: best_pass_rate={rate:.2f}, iterations={iters}",
        reply_markup=agent._main_keyboard(),
    )


async def cmd_fix(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._agent_registry:
        await update.message.reply_text("AgentRegistry не подключён.", reply_markup=agent._main_keyboard())
        return
    request = " ".join(context.args) if context.args else ""
    if not request:
        await update.message.reply_text(
            "Использование: /fix <что нужно исправить или интегрировать>",
            reply_markup=agent._main_keyboard(),
        )
        return
    await update.message.reply_text(
        "Принято. Запускаю self-improve пайплайн (анализ → код → тесты).",
        reply_markup=agent._main_keyboard(),
    )
    try:
        result = await agent._agent_registry.dispatch("self_improve", step=request)
        if result and result.success:
            await update.message.reply_text("Self-improve завершён успешно.", reply_markup=agent._main_keyboard())
        else:
            err = getattr(result, "error", "unknown")
            await update.message.reply_text(f"Self-improve завершён с ошибкой: {err}", reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Ошибка self-improve: {e}", reply_markup=agent._main_keyboard())


async def cmd_skills(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._skill_registry:
        await update.message.reply_text("SkillRegistry не подключён.", reply_markup=agent._main_keyboard())
        return
    skills = agent._skill_registry.list_skills(limit=20)
    if not skills:
        await update.message.reply_text("Реестр навыков пуст.", reply_markup=agent._main_keyboard())
        return
    lines = ["Навыки (последние 20):"]
    for s in skills:
        lines.append(
            f"- {s['name']} | {s['status']} | accept:{s.get('acceptance_status','?')} | sec:{s['security']} | v{s['version']}"
        )
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())


async def cmd_skills_pending(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._skill_registry:
        await update.message.reply_text("SkillRegistry не подключён.", reply_markup=agent._main_keyboard())
        return
    rows = agent._skill_registry.pending_skills(limit=30)
    if not rows:
        await update.message.reply_text("Нет pending навыков.", reply_markup=agent._main_keyboard())
        return
    lines = ["Pending skills (до acceptance):"]
    for r in rows:
        lines.append(f"- {r.get('name')} | {r.get('category','')} | updated:{r.get('updated_at','')}")
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())


async def cmd_skills_audit(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._skill_registry:
        await update.message.reply_text("SkillRegistry не подключён.", reply_markup=agent._main_keyboard())
        return
    try:
        audited = agent._skill_registry.audit_coverage()
        summary = agent._skill_registry.audit_summary(limit=8)
        lines = [
            "Skill Audit",
            f"Проверено: {audited}",
            f"Всего: {summary.get('total', 0)}",
            f"Stable: {summary.get('stable', 0)}",
            f"Pending: {summary.get('pending', 0)}",
            f"Rejected: {summary.get('rejected', 0)}",
            f"High risk: {summary.get('high_risk', 0)}",
        ]
        risky = summary.get("top_risky", []) or []
        if risky:
            lines.append("Top risk:")
            for row in risky[:5]:
                lines.append(
                    f"- {row.get('name')} | risk:{float(row.get('risk_score', 0.0)):.2f} | "
                    f"{row.get('compatibility')} | {row.get('acceptance_status')}"
                )
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Skill audit error: {e}", reply_markup=agent._main_keyboard())


async def cmd_skills_fix(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._skill_registry:
        await update.message.reply_text("SkillRegistry не подключён.", reply_markup=agent._main_keyboard())
        return
    try:
        result = agent._skill_registry.remediate_high_risk(limit=50)
        lines = [
            "Skill Remediation",
            f"Создано задач: {result.get('created', 0)}",
            f"Открыто задач: {result.get('open_total', 0)}",
        ]
        for item in (result.get("items", []) or [])[:5]:
            lines.append(
                f"- {item.get('skill_name')} | {item.get('reason')} | action: {item.get('action')}"
            )
        await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Skill remediation error: {e}", reply_markup=agent._main_keyboard())


async def cmd_playbooks(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    try:
        from modules.playbook_registry import PlaybookRegistry
        rows = PlaybookRegistry().top(limit=20)
    except Exception:
        rows = []
    if not rows:
        await update.message.reply_text("Реестр playbooks пуст.", reply_markup=agent._main_keyboard())
        return
    lines = ["Playbooks (top 20):"]
    for r in rows:
        lines.append(
            f"- {r.get('agent')}::{r.get('action')} "
            f"(ok:{r.get('success_count',0)} fail:{r.get('fail_count',0)})"
        )
    await update.message.reply_text("\n".join(lines), reply_markup=agent._main_keyboard())
