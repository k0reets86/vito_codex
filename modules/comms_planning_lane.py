from __future__ import annotations

import json
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes


async def cmd_deep(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    text = update.message.text.removeprefix("/deep").strip()
    if not text:
        await update.message.reply_text("Использование: /deep <тема для анализа>", reply_markup=agent._main_keyboard())
        return
    if not agent._judge_protocol:
        await update.message.reply_text("JudgeProtocol не подключён.", reply_markup=agent._main_keyboard())
        return
    if text.lower().startswith("brainstorm "):
        topic = text[len("brainstorm "):].strip()
        await update.message.reply_text(
            f"Запускаю brainstorm: {topic}\n"
            f"(Sonnet -> Perplexity -> GPT-5 -> Opus -> Perplexity -> Opus, ~$0.50-0.80)",
            reply_markup=agent._main_keyboard(),
        )
        try:
            result = await agent._judge_protocol.brainstorm(topic)
            formatted = agent._judge_protocol.format_brainstorm_for_telegram(result)
            if len(formatted) > 4000:
                parts = [formatted[i:i + 4000] for i in range(0, len(formatted), 4000)]
                for part in parts:
                    await update.message.reply_text(part, reply_markup=agent._main_keyboard())
            else:
                await update.message.reply_text(formatted, reply_markup=agent._main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"Ошибка brainstorm: {e}", reply_markup=agent._main_keyboard())
    else:
        await update.message.reply_text(f"Анализирую нишу: {text}...", reply_markup=agent._main_keyboard())
        try:
            verdict = await agent._judge_protocol.evaluate_niche(text)
            blocks: list[str] = [agent._judge_protocol.format_verdict_for_telegram(verdict)]
            if agent._agent_registry:
                try:
                    deep_result = await agent._agent_registry.dispatch(
                        "research",
                        step=text,
                        goal_title=f"Deep research: {text[:80]}",
                        content=text,
                    )
                    if deep_result and deep_result.success and deep_result.output:
                        meta = getattr(deep_result, "metadata", {}) or {}
                        top_ideas = list(meta.get("top_ideas") or [])
                        recommended_product = meta.get("recommended_product") if isinstance(meta.get("recommended_product"), dict) else {}
                        if agent._owner_task_state:
                            try:
                                agent._owner_task_state.enrich_active(
                                    research_topic=text[:200],
                                    research_report_path=str(meta.get("report_path") or "")[:500],
                                    research_options_json=json.dumps(top_ideas, ensure_ascii=False),
                                    research_recommended_json=json.dumps(recommended_product, ensure_ascii=False),
                                    selected_research_title=str((recommended_product or {}).get("title") or "")[:180],
                                )
                            except Exception:
                                pass
                        report = str(deep_result.output).strip()
                        if report:
                            blocks.append("Детальное исследование:\n" + report)
                        if top_ideas:
                            option_lines = []
                            for item in top_ideas[:5]:
                                option_lines.append(
                                    f"{int(item.get('rank', len(option_lines) + 1) or len(option_lines) + 1)}. "
                                    f"{str(item.get('title') or 'Idea').strip()} — "
                                    f"{int(item.get('score', 0) or 0)}/100 "
                                    f"[{str(item.get('platform') or 'gumroad').strip()}]"
                                )
                            blocks.append("Выбор для запуска:\n" + "\n".join(option_lines))
                except Exception as e:
                    blocks.append(f"Доп. исследование недоступно: {e}")
            formatted = "\n\n".join(blocks)
            if len(formatted) > 4000:
                parts = [formatted[i:i + 4000] for i in range(0, len(formatted), 4000)]
                for part in parts:
                    await update.message.reply_text(part, reply_markup=agent._main_keyboard())
            else:
                await update.message.reply_text(formatted, reply_markup=agent._main_keyboard())
            try:
                if agent._agent_registry:
                    q = await agent._agent_registry.dispatch(
                        "quality_review",
                        content=formatted[:6000],
                        content_type="deep_research_report",
                    )
                    if q and q.success and isinstance(getattr(q, "output", None), dict):
                        qout = q.output
                        q_msg = (
                            f"Финальный вердикт качества: "
                            f"{'OK' if bool(qout.get('approved', False)) else 'ПЕРЕДЕЛАТЬ'} "
                            f"(score={int(qout.get('score', 0) or 0)})."
                        )
                        await update.message.reply_text(q_msg, reply_markup=agent._main_keyboard())
            except Exception:
                pass
            if agent._conversation_engine:
                ideas: list[dict[str, Any]] = []
                recommended_item: dict[str, Any] | None = None
                if agent._owner_task_state:
                    try:
                        active = agent._owner_task_state.get_active() or {}
                        raw = str(active.get("research_options_json") or "").strip()
                        if raw:
                            parsed = json.loads(raw)
                            if isinstance(parsed, list):
                                ideas = [dict(item) for item in parsed[:5] if isinstance(item, dict)]
                        rec_raw = str(active.get("research_recommended_json") or "").strip()
                        if rec_raw:
                            rec_val = json.loads(rec_raw)
                            if isinstance(rec_val, dict):
                                recommended_item = dict(rec_val)
                    except Exception:
                        ideas = []
                        recommended_item = None
                agent._prime_research_pending_actions(
                    topic=text,
                    ideas=ideas,
                    recommended=recommended_item,
                    origin_text=f"deep:{text}",
                )
                await update.message.reply_text(
                    "Если ок — напиши «да» для рекомендованного варианта или просто номер варианта для точного запуска.",
                    reply_markup=agent._main_keyboard(),
                )
        except Exception as e:
            await update.message.reply_text(f"Ошибка анализа: {e}", reply_markup=agent._main_keyboard())
    agent._logger.info(f"Команда /deep выполнена: {text[:50]}", extra={"event": "cmd_deep"})


async def cmd_brainstorm(agent, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await agent._reject_stranger(update):
        return
    if not agent._judge_protocol:
        await update.message.reply_text("JudgeProtocol не подключён.", reply_markup=agent._main_keyboard())
        return
    text = update.message.text.removeprefix("/brainstorm").strip()
    if not text:
        await update.message.reply_text("Использование: /brainstorm <тема>", reply_markup=agent._main_keyboard())
        return
    await update.message.reply_text(
        f"Запускаю brainstorm: {text}\n"
        f"(Sonnet -> Perplexity -> GPT-5 -> Opus -> Perplexity -> Opus, ~$0.50-0.80)",
        reply_markup=agent._main_keyboard(),
    )
    try:
        result = await agent._judge_protocol.brainstorm(text)
        formatted = agent._judge_protocol.format_brainstorm_for_telegram(result)
        if len(formatted) > 4000:
            parts = [formatted[i:i + 4000] for i in range(0, len(formatted), 4000)]
            for part in parts:
                await update.message.reply_text(part, reply_markup=agent._main_keyboard())
        else:
            await update.message.reply_text(formatted, reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Ошибка brainstorm: {e}", reply_markup=agent._main_keyboard())
    agent._logger.info(f"Команда /brainstorm выполнена: {text[:50]}", extra={"event": "cmd_brainstorm"})


async def maybe_brainstorm_from_text(agent, update: Update, text: str) -> bool:
    if not agent._judge_protocol:
        return False
    if not text:
        return False
    lower = text.lower()
    trigger_words = ["брейншторм", "brainstorm", "мозговой штурм"]
    plan_words = ["план", "планирование", "стратег", "strategy", "roadmap", "расписание"]
    time_words = ["недел", "week", "weekly", "месяц", "month", "monthly", "квартал", "quarter", "год", "year"]
    wants_brainstorm = any(w in lower for w in trigger_words)
    wants_week_plan = any(p in lower for p in plan_words) and any(t in lower for t in time_words)
    if not wants_brainstorm and not wants_week_plan:
        return False
    if wants_week_plan and agent._weekly_planner:
        await update.message.reply_text(
            "Запускаю недельное планирование и стратегический брейншторм.",
            reply_markup=agent._main_keyboard(),
        )
        try:
            await agent._weekly_planner()
        except Exception as e:
            await update.message.reply_text(f"Ошибка недельного планирования: {e}", reply_markup=agent._main_keyboard())
        return True
    topic = text.strip()
    if len(topic) > 800:
        topic = topic[:800] + "…"
    await update.message.reply_text(
        f"Запускаю brainstorm: {topic}\n"
        f"(Sonnet -> Perplexity -> GPT-5 -> Opus -> Perplexity -> Opus, ~$0.50-0.80)",
        reply_markup=agent._main_keyboard(),
    )
    try:
        result = await agent._judge_protocol.brainstorm(topic)
        formatted = agent._judge_protocol.format_brainstorm_for_telegram(result)
        if len(formatted) > 4000:
            parts = [formatted[i:i + 4000] for i in range(0, len(formatted), 4000)]
            for part in parts:
                await update.message.reply_text(part, reply_markup=agent._main_keyboard())
        else:
            await update.message.reply_text(formatted, reply_markup=agent._main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Ошибка brainstorm: {e}", reply_markup=agent._main_keyboard())
    return True


async def maybe_schedule_from_text(agent, update: Update, text: str) -> bool:
    if not agent._schedule_manager:
        return False
    if not text:
        return False
    from modules.schedule_parser import parse_schedule
    result = parse_schedule(text)
    if not result.ok:
        if result.needs_clarification:
            await update.message.reply_text(result.clarification or "Уточни дату/время.", reply_markup=agent._main_keyboard())
            return True
        return False
    lower = text.lower()
    is_update = any(w in lower for w in ("перенеси", "перенести", "сдвинь", "измени", "изменить", "update", "reschedule", "move"))
    is_delete = any(w in lower for w in ("отмени", "удали", "удалить", "cancel", "remove"))
    similar = agent._schedule_manager.find_similar(text, action=result.action)
    if is_delete and similar:
        if len(similar) > 1:
            options = "\n".join([f"{i+1}. #{t.id} — {t.title}" for i, t in enumerate(similar)])
            agent._pending_schedule_update = {"choices": similar, "new_schedule": None, "mode": "delete"}
            await update.message.reply_text(
                "Уточни, какое расписание удалить:\n" + options,
                reply_markup=agent._main_keyboard(),
            )
            return True
        agent._schedule_manager.delete_task(similar[0].id)
        await update.message.reply_text(
            f"Готово. Расписание #{similar[0].id} удалено.",
            reply_markup=agent._main_keyboard(),
        )
        return True
    if is_update and similar:
        if len(similar) > 1:
            options = "\n".join([f"{i+1}. #{t.id} — {t.title}" for i, t in enumerate(similar)])
            agent._pending_schedule_update = {"choices": similar, "new_schedule": result, "mode": "update"}
            await update.message.reply_text(
                "Уточни, какое расписание обновить:\n" + options,
                reply_markup=agent._main_keyboard(),
            )
            return True
        agent._schedule_manager.update_task(
            similar[0].id,
            schedule_type=result.schedule_type,
            time_of_day=result.time_of_day,
            weekday=result.weekday,
            run_at=result.run_at,
        )
        await update.message.reply_text(
            f"Готово. Расписание #{similar[0].id} обновлено.",
            reply_markup=agent._main_keyboard(),
        )
        return True
    if similar:
        options = "\n".join([f"{i+1}. #{t.id} — {t.title}" for i, t in enumerate(similar)])
        agent._pending_schedule_update = {"choices": similar, "new_schedule": result, "mode": "update"}
        await update.message.reply_text(
            "Похоже, такое расписание уже есть. Обновить его?\n"
            "Ответь номером:\n" + options,
            reply_markup=agent._main_keyboard(),
        )
        return True
    task_id = agent._schedule_manager.add_task(
        title=result.title or text[:120],
        action=result.action or "reminder",
        schedule_type=result.schedule_type or "once",
        time_of_day=result.time_of_day,
        weekday=result.weekday,
        run_at=result.run_at,
    )
    when = ""
    if result.schedule_type == "daily":
        when = f"ежедневно в {result.time_of_day}"
    elif result.schedule_type == "weekly":
        when = f"еженедельно в {result.time_of_day}"
    elif result.schedule_type == "once":
        when = f"{result.run_at}"
    await update.message.reply_text(
        f"Готово. Поставил задачу #{task_id}: {when}.",
        reply_markup=agent._main_keyboard(),
    )
    return True
