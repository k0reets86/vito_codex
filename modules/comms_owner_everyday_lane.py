from __future__ import annotations


def _norm(text: str) -> str:
    return str(text or "").strip().lower().replace("ё", "е")


def is_how_are_you_prompt(text: str) -> bool:
    s = _norm(text)
    if not s:
        return False
    return any(
        token in s
        for token in (
            "как дела",
            "как дел",
            "как ты",
            "че по задач",
            "что по задач",
            "что с задач",
            "что сейчас делаешь",
            "что щас делаеш",
            "че щас делаеш",
            "че сейчас делаеш",
            "че щас делаешь",
            "че сейчас делаешь",
            "что сейчас делаеш",
            "как успехи",
        )
    )


def is_pause_prompt(text: str) -> bool:
    return _norm(text) in {"стоп", "пауза", "остановись", "останови все", "прекрати", "pause"}


def is_resume_prompt(text: str) -> bool:
    return _norm(text) in {"продолжай", "продолжим", "поехали", "resume", "возобнови", "возобновляй"}


def is_cancel_all_tasks_prompt(text: str) -> bool:
    s = _norm(text)
    if not s:
        return False
    short_all_patterns = {
        "отмени все",
        "отмена всего",
        "сними все",
        "убери все",
        "очисти все",
        "cancel all",
        "stop all",
    }
    if s in short_all_patterns:
        return True
    task_tokens = ("задач", "цели", "дела", "очеред")
    cancel_tokens = ("отмени", "отмена", "сними", "убери", "очисти", "stop all", "cancel all")
    all_tokens = ("все", "всё", "all")
    return any(tok in s for tok in cancel_tokens) and any(tok in s for tok in all_tokens) and any(tok in s for tok in task_tokens)


def is_what_do_you_need_prompt(text: str) -> bool:
    return _norm(text) in {"что от меня нужно", "что от меня надо", "что нужно от меня", "что тебе нужно", "что от меня требуется"}


def is_what_is_ready_prompt(text: str) -> bool:
    return _norm(text) in {"что уже готово", "что готово", "что уже сделал", "что уже сделано"}


def is_what_should_i_do_prompt(text: str) -> bool:
    return _norm(text) in {"что мне делать", "что мне сейчас делать", "что дальше делать мне"}


def is_do_not_publish_prompt(text: str) -> bool:
    return _norm(text) in {"не публикуй", "не публикуй пока", "пока не публикуй", "не надо публиковать"}


def is_remove_this_prompt(text: str) -> bool:
    return _norm(text) in {"убери это", "убери", "сними это", "убери пока"}


def is_do_not_do_now_prompt(text: str) -> bool:
    return _norm(text) in {"сейчас не делай", "не делай сейчас", "пока не делай"}


def is_not_understood_prompt(text: str) -> bool:
    return _norm(text) in {"не понял", "не поняла", "непонятно", "не понял тебя"}


def is_why_stopped_prompt(text: str) -> bool:
    return _norm(text) in {"почему остановился", "почему встал", "почему стоп"}


def is_do_not_touch_old_prompt(text: str) -> bool:
    s = _norm(text)
    return ("не трогай" in s and any(tok in s for tok in ("стар", "опублик", "прошл"))) or s in {
        "старое не трогай",
        "не трогай старое",
        "не трогай опубликованное",
    }


def is_create_new_prompt(text: str) -> bool:
    return _norm(text) in {"создай новое", "создай новый", "сделай новое", "новое создай"}


def is_postpone_prompt(text: str) -> bool:
    return _norm(text) in {"ладно потом", "потом", "позже", "давай потом", "отложи пока"}


def is_nevermind_prompt(text: str) -> bool:
    return _norm(text) in {"не надо", "не нужно", "отмена", "забей", "отбой"}


def render_owner_brief_status(agent) -> str:
    running = False
    if agent._decision_loop:
        try:
            st = agent._decision_loop.get_status() or {}
            running = bool(st.get("running", False))
        except Exception:
            pass
    active_text = ""
    if agent._owner_task_state:
        try:
            active = agent._owner_task_state.get_active() or {}
            active_text = str(active.get("text") or "").strip()
        except Exception:
            pass
    pending_approvals = len(getattr(agent, "_pending_approvals", {}) or {})
    queued = 0
    if agent._goal_engine:
        try:
            goals = agent._goal_engine.get_all_goals(status=None) or []
            queued = sum(
                1
                for g in goals
                if str(getattr(getattr(g, "status", None), "value", "") or "")
                not in {"completed", "failed", "cancelled"}
            )
        except Exception:
            pass
    lines = []
    if active_text:
        lines.append(f"Сейчас в работе: {active_text[:200]}")
    else:
        lines.append("Сейчас активной задачи от тебя не зафиксировано.")
    lines.append(f"Decision Loop: {'работает' if running else 'на паузе'}.")
    if pending_approvals:
        lines.append(f"Ожидают подтверждения: {pending_approvals}.")
    if queued:
        lines.append(
            f"В системной очереди еще {queued}. Если это старые хвосты, напиши: «отмени все задачи»."
        )
    return "\n".join(lines)


def cancel_all_owner_work(agent, reason: str = "owner_cancelled") -> int:
    if agent._cancel_state:
        try:
            agent._cancel_state.cancel(reason=reason)
        except Exception:
            pass
    cancelled_goals = agent._cancel_goal_queue(reason=reason)
    if agent._owner_task_state:
        try:
            agent._owner_task_state.cancel(note=reason)
        except Exception:
            pass
    agent._pending_approvals.clear()
    agent._pending_schedule_update = None
    agent._pending_owner_confirmation = None
    agent._pending_choice_context = None
    agent._pending_system_action = None
    if agent._decision_loop:
        try:
            agent._decision_loop.stop()
        except Exception:
            pass
    return int(cancelled_goals or 0)
