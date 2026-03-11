from __future__ import annotations

from typing import Any


def get_available_actions(engine) -> str:
    actions = []
    if engine.agent_registry:
        caps = set()
        for a in engine.agent_registry.get_all_statuses():
            caps.update(a.get("capabilities", []))
        actions.append(f'dispatch_agent(task_type) — запуск агента (доступные: {", ".join(sorted(caps)[:15])})')
        actions.append("scan_trends() — сканировать тренды")
        actions.append("scan_reddit() — сканировать Reddit")
        actions.append("register_account(url, form, submit_selector, code_selector, ...) — регистрация с email-кодом")
        actions.append("learn_service(service) — изучить платформу/сервис и собрать профиль")
        actions.append("onboard_platform(platform_name) — провести онбординг платформы до регистрации в VITO")
    if engine.goal_engine:
        actions.append("cancel_goal(goal_id) — отменить цель")
        actions.append("change_priority(goal_id, priority) — сменить приоритет (CRITICAL/HIGH/MEDIUM/LOW)")
    if engine.decision_loop:
        actions.append("stop_loop() — остановить Decision Loop")
        actions.append("start_loop() — запустить Decision Loop")
    if engine.self_healer:
        actions.append("check_errors() — проверить ошибки системы")
    if engine.judge_protocol:
        actions.append("analyze_niche(topic, deep=false) — анализ ниши (1 модель, deep=true для 4 моделей)")
    if engine.knowledge_updater:
        actions.append("update_knowledge() — обновить базу знаний и цены моделей")
    if engine.self_updater:
        actions.append("create_backup() — создать бэкап кода")
    if engine.code_generator:
        actions.append("apply_code_change(file, instruction) — изменить код файла через LLM (backup + test)")
    if engine.agent_registry:
        actions.append("self_improve(request) — самонастройка: анализ → код → тесты")
        actions.append("learn_service(service) — изучить сервис и добавить в базу знаний")
        actions.append("run_deep_research(topic) — глубокое исследование с источниками")
        actions.append("run_product_pipeline(topic, platforms, auto_publish=false) — сквозной pipeline товара")
        actions.append("run_kdp_draft_maintenance(target_title, language) — заполнить метаданные KDP-драфта")
        actions.append("run_platform_task(platform, request) — универсальный раннер платформенных задач")
        actions.append("run_printful_etsy_sync(topic, auto_publish=true) — создать POD товар в Printful и проверить Etsy")
        actions.append("run_improvement_cycle(request) — backup + HR + research + self-improve")
        actions.append("autonomous_execute(request) — выполнить задачу или доучиться и выполнить")
    return "\n".join(f"  - {a}" for a in actions) if actions else "(нет действий)"


def allowed_actions(engine) -> set[str]:
    allowed: set[str] = set()
    if engine.agent_registry:
        allowed.update({"dispatch_agent", "scan_trends", "scan_reddit"})
    if engine.goal_engine:
        allowed.update({"cancel_goal", "change_priority"})
    if engine.decision_loop:
        allowed.update({"stop_loop", "start_loop"})
    if engine.self_healer:
        allowed.add("check_errors")
    if engine.judge_protocol:
        allowed.add("analyze_niche")
    if engine.knowledge_updater:
        allowed.add("update_knowledge")
    if engine.self_updater:
        allowed.add("create_backup")
    if engine.code_generator:
        allowed.add("apply_code_change")
    if engine.agent_registry:
        allowed.update({
            "self_improve",
            "learn_service",
            "onboard_platform",
            "register_account",
            "run_deep_research",
            "run_product_pipeline",
            "run_kdp_draft_maintenance",
            "run_platform_task",
            "run_printful_etsy_sync",
            "run_improvement_cycle",
            "autonomous_execute",
            "run_autonomy_proposal",
        })
    return allowed


async def autonomous_execute(engine, request: str) -> str:
    if not engine.agent_registry:
        return "AgentRegistry недоступен."

    capability = engine._infer_capability(request)
    attempts: list[str] = []
    low_req = str(request or "").lower()
    if any(k in low_req for k in ("amazon", "амазон", "kdp", "кдп")) and any(
        k in low_req for k in ("удали", "удалить", "редакт", "заполни", "draft", "книг")
    ):
        return (
            "По Amazon KDP сейчас доступны только: вход и проверка инвентаря. "
            "Операции удаления/редактирования драфтов ещё не реализованы в безопасном автоконтуре."
        )

    async def _run_cap(cap: str) -> tuple[bool, str]:
        if not cap:
            return False, "capability_not_detected"
        try:
            res = await engine.agent_registry.dispatch(cap, step=request, content=request, goal_title=request[:120])
        except Exception as e:
            return False, f"dispatch_exception:{e}"
        if res and res.success:
            out = getattr(res, "output", None)
            txt = str(out)[:900] if out is not None else "completed"
            return True, txt
        return False, getattr(res, "error", "dispatch_failed") if res else "dispatch_none"

    ok, detail = await _run_cap(capability)
    attempts.append(f"run:{capability or 'unknown'}:{'ok' if ok else detail}")
    if ok:
        q_verdict = await engine._maybe_quality_gate(capability, request, detail)
        attempts.append(f"quality:{q_verdict}")
        if q_verdict.startswith("rework"):
            ok_re, detail_re = await _run_cap(capability)
            attempts.append(f"rework:{capability or 'unknown'}:{'ok' if ok_re else detail_re}")
            if ok_re:
                detail = detail_re
                q_verdict = await engine._maybe_quality_gate(capability, request, detail_re)
                attempts.append(f"quality_after_rework:{q_verdict}")
        engine._record_autonomy_learning(
            request=request,
            capability=capability or "unknown",
            success=not q_verdict.startswith("rework"),
            attempts=attempts,
            result_text=detail,
        )
        if q_verdict.startswith("rework"):
            return (
                f"Задача выполнена технически ({capability}), но качество требует доработки.\n"
                f"Quality gate: {q_verdict}\n"
                f"Шаги: {' | '.join(attempts)}"
            )
        return f"Задача выполнена ({capability}).\nQuality gate: {q_verdict}\nРезультат: {detail}"

    if bool(getattr(engine.settings, "AUTONOMY_AUTO_LEARN_ON_FAILURE", True)):
        try:
            rr = await engine.agent_registry.dispatch("research", step=request, topic=request, goal_title=f"Auto-learn: {request[:80]}")
            attempts.append(f"learn:research:{'ok' if rr and rr.success else 'fail'}")
        except Exception as e:
            attempts.append(f"learn:research_exception:{e}")

    if bool(getattr(engine.settings, "AUTONOMY_AUTO_SELF_IMPROVE_ON_MISS", False)):
        try:
            si = await engine.agent_registry.dispatch("self_improve", step=f"Improve capability for request: {request}")
            attempts.append(f"learn:self_improve:{'ok' if si and si.success else 'fail'}")
        except Exception as e:
            attempts.append(f"learn:self_improve_exception:{e}")

    ok2, detail2 = await _run_cap(capability)
    attempts.append(f"retry:{capability or 'unknown'}:{'ok' if ok2 else detail2}")
    if ok2:
        q2 = await engine._maybe_quality_gate(capability, request, detail2)
        attempts.append(f"quality:{q2}")
        engine._record_autonomy_learning(
            request=request,
            capability=capability or "unknown",
            success=not q2.startswith("rework"),
            attempts=attempts,
            result_text=detail2,
        )
        return (
            f"Задача выполнена после обучения ({capability}).\n"
            f"Quality gate: {q2}\n"
            f"Результат: {detail2}\n"
            f"Шаги: {' | '.join(attempts)}"
        )

    try:
        core = engine.agent_registry.get("vito_core") if hasattr(engine.agent_registry, "get") else None
        if core is not None:
            res = await core.execute_task("orchestrate", step=request, goal_title=request[:120])
            if res and res.success:
                q3 = await engine._maybe_quality_gate("orchestrate", request, str(getattr(res, "output", "")))
                attempts.append(f"quality:{q3}")
                engine._record_autonomy_learning(
                    request=request,
                    capability="orchestrate",
                    success=not q3.startswith("rework"),
                    attempts=attempts,
                    result_text=str(getattr(res, "output", "")),
                )
                return (
                    "Задача выполнена через оркестратор.\n"
                    f"Quality gate: {q3}\n"
                    f"Результат: {str(getattr(res, 'output', ''))[:900]}\n"
                    f"Шаги: {' | '.join(attempts)}"
                )
    except Exception as e:
        attempts.append(f"fallback:orchestrate_exception:{e}")

    engine._record_autonomy_learning(
        request=request,
        capability=capability or "unknown",
        success=False,
        attempts=attempts,
        result_text="",
    )
    return (
        "Автономный контур не смог завершить задачу с текущими навыками.\n"
        "Я сохранил попытки в память ошибок и продолжу дообучение по этой теме.\n"
        f"Шаги: {' | '.join(attempts[:8])}"
    )


def infer_capability(engine, request: str) -> str:
    text = str(request or "").strip()
    if not text:
        return ""
    skill_cap = engine._pick_capability_from_memory(text)
    if skill_cap:
        return skill_cap
    try:
        core = engine.agent_registry.get("vito_core") if hasattr(engine.agent_registry, "get") else None
        if core and hasattr(core, "classify_step"):
            cap = core.classify_step(text)
            if cap:
                return str(cap)
    except Exception:
        pass
    s = engine._normalize_for_nlu(text)
    mapping = [
        (("исслед", "research", "анализ", "deep"), "research"),
        (("тренд", "niche", "ниш"), "trend_scan"),
        (("seo", "ключев", "keyword", "мета"), "listing_seo_pack"),
        (("пост", "tweet", "соц", "smm"), "social_media"),
        (("товар", "листинг", "publish", "продукт"), "product_pipeline"),
        (("перевод", "translate", "localize"), "translate"),
        (("юрид", "tos", "gdpr", "copyright"), "legal"),
        (("финанс", "юнит", "цена", "pricing"), "unit_economics"),
        (("документ", "report", "отчет"), "documentation"),
    ]
    for keys, cap in mapping:
        if any(k in s for k in keys):
            return cap
    return "orchestrate"


def pick_capability_from_memory(engine, request: str) -> str:
    mm = engine.memory
    if mm is None or not hasattr(mm, "search_skills"):
        return ""
    try:
        rows = mm.search_skills(request, limit=5)
    except Exception:
        return ""
    if not isinstance(rows, list):
        return ""
    best_cap = ""
    best_score = -(10**9)
    for r in rows:
        if not isinstance(r, dict):
            continue
        cap = str(r.get("task_type") or "").strip()
        if not cap:
            continue
        succ = int(r.get("success_count", 0) or 0)
        fail = int(r.get("fail_count", 0) or 0)
        score = (succ * 2) - fail
        if score > best_score:
            best_score = score
            best_cap = cap
    return best_cap


async def maybe_quality_gate(engine, capability: str, request: str, output_text: str) -> str:
    if not engine.agent_registry:
        return "skipped(no_registry)"
    cap = str(capability or "").strip().lower()
    if cap not in {
        "research", "content_creation", "product_pipeline", "social_media",
        "listing_create", "publish", "documentation", "seo", "listing_seo_pack",
    }:
        return "skipped(not_required)"
    try:
        q = await engine.agent_registry.dispatch(
            "quality_review",
            content=f"capability={cap}\nrequest={request[:400]}\noutput={str(output_text)[:5000]}",
            content_type=f"autonomy_{cap}",
        )
        if q and q.success and isinstance(getattr(q, "output", None), dict):
            qo = q.output
            approved = bool(qo.get("approved", False))
            score = int(qo.get("score", 0) or 0)
            return ("ok" if approved else "rework") + f"(score={score})"
        return "skipped(quality_unavailable)"
    except Exception as e:
        return f"skipped(quality_error:{e})"


def record_autonomy_learning(
    engine,
    request: str,
    capability: str,
    success: bool,
    attempts: list[str],
    result_text: str,
) -> None:
    mm = engine.memory
    if mm is None:
        return
    skill_name = f"autonomy:{capability}"
    try:
        mm.save_skill(
            name=skill_name,
            description=f"Autonomous loop for '{request[:80]}'",
            agent="conversation_engine",
            task_type=capability,
            method={
                "request": request[:240],
                "attempts": attempts[:10],
                "success": bool(success),
            },
        )
        mm.update_skill_success(skill_name, success=bool(success))
        mm.update_skill_last_result(skill_name, str(result_text or "")[:500])
    except Exception:
        pass
    try:
        if success:
            mm.save_pattern(
                category="autonomy_success",
                key=f"{capability}:{hash(request) % 100000}",
                value=" | ".join(attempts[:8]),
                confidence=0.85,
            )
        else:
            mm.save_pattern(
                category="anti_pattern",
                key=f"autonomy_fail:{capability}:{hash(request) % 100000}",
                value=" | ".join(attempts[:8]),
                confidence=0.95,
            )
            mm.log_error(
                module="conversation_engine",
                error_type="autonomous_execute_failed",
                message=f"{capability}: {request[:180]}",
                resolution="auto_learn_retry_scheduled",
            )
    except Exception:
        pass
