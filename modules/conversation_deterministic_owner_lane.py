from __future__ import annotations

import json
import re
from typing import Any


def format_deep_research_owner_report(
    *,
    topic: str,
    summary: str,
    score: int,
    verdict: str,
    sources: list[str],
    report_path: str = "",
    top_ideas: list[dict[str, Any]] | None = None,
    recommended_product: dict[str, Any] | None = None,
) -> str:
    src = ", ".join(sorted({str(s).strip() for s in (sources or []) if str(s).strip()})) or "not_detected"
    status = "ok" if str(verdict).lower() == "ok" else "rework"
    body = str(summary or "").strip()
    if len(body) > 3500:
        body = body[:3500].rstrip() + "\n..."
    ideas_block = ""
    items = list(top_ideas or [])[:5]
    if items:
        lines = []
        for item in items:
            lines.append(
                f"{int(item.get('rank', len(lines) + 1) or len(lines) + 1)}. "
                f"{str(item.get('title') or 'Idea').strip()} — "
                f"{int(item.get('score', 0) or 0)}/100 "
                f"[{str(item.get('platform') or 'platform?').strip()}]"
            )
        ideas_block = "Топ-варианты:\n" + "\n".join(lines) + "\n\n"
    rec = dict(recommended_product or {})
    rec_block = ""
    if rec:
        rec_block = (
            "Рекомендую сейчас:\n"
            f"- {str(rec.get('title') or topic).strip()} — {int(rec.get('score', 0) or 0)}/100\n"
            f"- platform: {str(rec.get('platform') or 'gumroad').strip()}\n"
            f"- why now: {str(rec.get('why_now') or '').strip()[:220]}\n\n"
        )
    return (
        f"Глубокое исследование готово: {topic}\n\n"
        f"Quality gate: {status} (score={int(score or 0)}).\n"
        f"Источники: {src}\n\n"
        f"{rec_block}"
        f"{ideas_block}"
        f"Результат:\n{body}\n\n"
        f"Полный отчёт: {report_path or 'не сохранён'}\n\n"
        "Можно ответить просто номером варианта или фразой вроде "
        "«создавай», «вариант 2 на etsy», «делай рекомендованный»."
    )


def maybe_continue_from_research_state(engine: Any, text: str) -> dict[str, Any] | None:
    if not engine.owner_task_state:
        return None
    try:
        active = engine.owner_task_state.get_active() or {}
    except Exception:
        return None
    raw = str(active.get("research_options_json") or "").strip()
    if not raw:
        return None
    try:
        ideas = json.loads(raw)
    except Exception:
        return None
    if not isinstance(ideas, list) or not ideas:
        return None
    lower = str(text or "").strip().lower()
    choice_match = re.search(r"(?<!\d)([1-5])(?!\d)", lower)
    selected_idx = int(choice_match.group(1)) if choice_match else 0
    selected: dict[str, Any] | None = None
    if selected_idx and 1 <= selected_idx <= len(ideas):
        candidate = ideas[selected_idx - 1]
        if isinstance(candidate, dict):
            selected = candidate
    elif any(tok in lower for tok in ("рекоменд", "recommended", "этот", "this one")):
        try:
            selected = json.loads(str(active.get("research_recommended_json") or "{}"))
        except Exception:
            selected = None
    elif str(active.get("selected_research_json") or "").strip():
        try:
            selected = json.loads(str(active.get("selected_research_json")))
        except Exception:
            selected = None
    if selected_idx and selected:
        engine.owner_task_state.enrich_active(
            selected_research_option=selected_idx,
            selected_research_json=json.dumps(selected, ensure_ascii=False),
            selected_research_title=str(selected.get("title") or "")[:180],
        )
        try:
            engine.owner_model.update_from_decision(selected, approved=True)
        except Exception:
            pass
        if lower.isdigit() or "вариант" in lower:
            return {
                "intent": engine.Intent.QUESTION.value,
                "response": (
                    f"Зафиксировал вариант {selected_idx}: {str(selected.get('title') or '').strip()} "
                    f"({int(selected.get('score', 0) or 0)}/100). "
                    "Если запускать сразу, напиши: «создавай» или укажи платформу."
                ),
            }
    create_like = any(k in lower for k in ("создавай", "сделай", "публикуй", "запускай", "делай", "launch", "publish", "create"))
    if not create_like or not isinstance(selected, dict):
        return None
    platforms = engine._extract_platforms(text)
    explicit_platform_request = bool(platforms)
    default_platform = str(selected.get("platform") or "").strip().lower()
    if not explicit_platform_request and default_platform and default_platform not in platforms:
        platforms = [default_platform] + [p for p in platforms if p != default_platform]
    if not platforms:
        platforms = [default_platform or "gumroad"]
    topic = str(selected.get("title") or active.get("selected_research_title") or active.get("text") or "Digital Product Starter Kit").strip()
    try:
        engine.owner_task_state.enrich_active(
            selected_research_json=json.dumps(selected, ensure_ascii=False),
            selected_research_title=topic[:180],
            selected_research_platform=",".join(platforms),
        )
    except Exception:
        pass
    return {
        "intent": engine.Intent.SYSTEM_ACTION.value,
        "response": f"Принял. Собираю и публикую: {topic} ({', '.join(platforms)}).",
        "actions": [{"action": "run_product_pipeline", "params": {"topic": topic, "platforms": platforms, "auto_publish": True}}],
        "needs_confirmation": False,
    }


def maybe_continue_from_autonomy_proposals(engine: Any, text: str) -> dict[str, Any] | None:
    if not engine.owner_task_state:
        return None
    try:
        active = engine.owner_task_state.get_active() or {}
    except Exception:
        active = {}
    try:
        proposal_ids = json.loads(str(active.get("autonomy_proposal_ids_json") or "[]"))
    except Exception:
        proposal_ids = []
    proposals: list[dict[str, Any]] = []
    if isinstance(proposal_ids, list):
        for raw_id in proposal_ids[:5]:
            try:
                proposal_id = int(raw_id or 0)
            except Exception:
                proposal_id = 0
            if proposal_id <= 0:
                continue
            item = engine.autonomy_proposals.get(proposal_id)
            if isinstance(item, dict):
                proposals.append(item)
    if not proposals:
        raw = str(active.get("autonomy_proposals_json") or "").strip()
        if not raw:
            return None
        try:
            proposals = json.loads(raw)
        except Exception:
            return None
        if not isinstance(proposals, list) or not proposals:
            return None
    lower = str(text or "").strip().lower()
    choice_match = re.search(r"(?<!\d)([1-5])(?!\d)", lower)
    selected_idx = int(choice_match.group(1)) if choice_match else 0
    selected = None
    if selected_idx and 1 <= selected_idx <= len(proposals):
        candidate = proposals[selected_idx - 1]
        if isinstance(candidate, dict):
            selected = candidate
    else:
        try:
            selected_id = int(active.get("autonomy_selected_proposal_id") or 0)
        except Exception:
            selected_id = 0
        if selected_id > 0:
            selected = engine.autonomy_proposals.get(selected_id)
        elif str(active.get("autonomy_selected_json") or "").strip():
            try:
                selected = json.loads(str(active.get("autonomy_selected_json")))
            except Exception:
                selected = None
    if selected_idx and selected:
        try:
            engine.owner_task_state.enrich_active(
                autonomy_selected_index=selected_idx,
                autonomy_selected_proposal_id=int(selected.get("proposal_id") or 0),
                autonomy_selected_json="",
                autonomy_selected_title=str(selected.get("title") or "")[:180],
            )
        except Exception:
            pass
        if lower.isdigit() or "вариант" in lower:
            return {
                "intent": engine.Intent.QUESTION.value,
                "response": (
                    f"Зафиксировал автономное предложение {selected_idx}: "
                    f"{str(selected.get('title') or '').strip()}. "
                    "Можно ответить «одобряю», «отложи» или «запускай»."
                ),
            }
    if not isinstance(selected, dict):
        return None
    proposal_id = int(selected.get("proposal_id") or 0)
    if any(tok in lower for tok in ("отлож", "потом", "не сейчас", "defer")):
        if proposal_id > 0:
            engine.autonomy_proposals.mark_status(proposal_id, "deferred", note="owner_deferred")
        return {"intent": engine.Intent.QUESTION.value, "response": "Отложил предложение. Оно останется в списке."}
    if any(tok in lower for tok in ("нет", "отклон", "reject")):
        if proposal_id > 0:
            engine.autonomy_proposals.mark_status(proposal_id, "rejected", note="owner_rejected")
        return {"intent": engine.Intent.QUESTION.value, "response": "Отклонил предложение и убрал его из активных."}
    if any(tok in lower for tok in ("одобр", "да", "запуск", "делай", "run")):
        if proposal_id > 0:
            engine.autonomy_proposals.mark_status(proposal_id, "approved", note="owner_approved")
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": f"Принял. Запускаю автономное предложение: {str(selected.get('title') or '').strip()}",
            "actions": [{
                "action": "run_autonomy_proposal",
                "params": {
                    "proposal_id": proposal_id,
                    "proposal_kind": str(selected.get("proposal_kind") or ""),
                    "proposal": dict(selected.get("payload") or {}),
                },
            }],
            "needs_confirmation": False,
        }
    return None


async def deterministic_owner_route(engine: Any, text: str) -> dict[str, Any] | None:
    if str(text or "").strip().startswith("/"):
        return None
    normalized = engine._normalize_for_nlu(text)
    if (
        engine._has_keywords(normalized, ("printful", "принтфул"), fuzzy=True)
        and engine._has_keywords(normalized, ("etsy", "этси", "етси"), fuzzy=True)
        and engine._looks_like_imperative_request(text)
    ):
        actions = [{"action": "run_printful_etsy_sync", "params": {"topic": engine._extract_product_topic(text), "auto_publish": True}}]
        engine._ensure_owner_task_state(text, engine.Intent.SYSTEM_ACTION.value)
        if engine._defer_owner_actions:
            return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": "Запускаю связку Printful → Etsy (создание POD-товара и проверка листинга). Принял в выполнение.", "actions": actions, "needs_confirmation": False}
        out = await engine._execute_actions(actions)
        return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Запускаю связку Printful → Etsy (создание POD-товара и проверка листинга).\n{out or 'Принял в выполнение.'}", "actions": actions, "needs_confirmation": False}
    platform_key = engine._extract_platform_key(text)
    platform_op_kw = (
        "зайди", "зайти", "войди", "войти", "вход", "логин", "auth", "авториз", "сесс",
        "статус аккаунта", "состояние аккаунта", "проверь аккаунт",
        "товар", "листинг", "inventory", "status", "account",
        "publish", "опубликуй", "редакт", "заполни", "draft",
        "пост", "tweet", "твит", "анонс",
    )
    if platform_key and engine._looks_like_imperative_request(text) and engine._has_keywords(normalized, platform_op_kw, fuzzy=True):
        actions = [{"action": "run_platform_task", "params": {"platform": platform_key, "request": text}}]
        engine._ensure_owner_task_state(text, engine.Intent.SYSTEM_ACTION.value)
        if engine._defer_owner_actions:
            return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Запускаю задачу на платформе {platform_key}. Принял в выполнение.", "actions": actions, "needs_confirmation": False}
        out = await engine._execute_actions(actions)
        return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Запускаю задачу на платформе {platform_key}.\n{out or 'Принял в выполнение.'}", "actions": actions, "needs_confirmation": False}
    complaint_kw = ("не вижу", "ничего не делаешь", "не делаешь", "завис", "висит", "что с задачей")
    if engine._has_keywords(normalized, complaint_kw, fuzzy=True):
        return {"intent": engine.Intent.QUESTION.value, "response": engine._quick_status()}
    status_kw = ("статус", "status", "как дела", "что по задач", "активные задач", "progress", "прогресс")
    if engine._has_keywords(normalized, status_kw, fuzzy=True):
        return {"intent": engine.Intent.QUESTION.value, "response": engine._quick_status()}
    platform_summary_kw = ("сводк", "summary", "overview")
    platform_kw = ("платформ", "platforms")
    if engine._has_keywords(normalized, platform_summary_kw, fuzzy=True) and engine._has_keywords(normalized, platform_kw, fuzzy=True):
        active = engine.owner_task_state.get_active() if engine.owner_task_state else {}
        topic = str((active or {}).get("selected_research_title") or (active or {}).get("text") or "текущему продукту").strip()
        return {"intent": engine.Intent.QUESTION.value, "response": f"Короткая сводка по платформам для {topic}:\n- Etsy: основной marketplace-листинг и упаковка карточки товара.\n- Gumroad: прямая продажа цифрового продукта с файлом и предпросмотром.\n- KDP: книжная версия для Kindle/print, если продукт идет как книга или workbook."}
    autonomy_kw = ("предлож", "идеи", "автоном", "что нашел", "что нашёл", "opportunit", "opportunity")
    if engine._has_keywords(normalized, autonomy_kw, fuzzy=True):
        items = engine.autonomy_proposals.list_open(limit=5)
        if not items:
            return {"intent": engine.Intent.QUESTION.value, "response": "Автономных предложений пока нет."}
        lines = ["Текущие автономные предложения:"]
        for idx, item in enumerate(items, start=1):
            payload = dict(item.get("payload") or {})
            lines.append(f"{idx}. {str(item.get('title') or '').strip()} — {str(item.get('proposal_kind') or '').strip()} (score={round(float(item.get('score') or 0.0), 2)})")
            why = str(payload.get("why") or payload.get("rationale") or "").strip()
            if why:
                lines.append(f"   {why[:160]}")
        lines.append("Можно ответить номером, «одобряю 2», «отложи 1» или «запускай 3».")
        try:
            if engine.owner_task_state:
                active = engine.owner_task_state.get_active() or {}
                if not active:
                    engine.owner_task_state.set_active(text=text, source="telegram", intent=engine.Intent.QUESTION.value, force=False, metadata={"autonomy_lane": True})
                proposal_ids = [int(item.get("proposal_id") or 0) for item in items[:5] if int(item.get("proposal_id") or 0) > 0]
                engine.owner_task_state.enrich_active(autonomy_proposal_ids_json=json.dumps(proposal_ids, ensure_ascii=False), autonomy_selected_json="", autonomy_selected_proposal_id="")
        except Exception:
            pass
        return {"intent": engine.Intent.QUESTION.value, "response": "\n".join(lines)}
    net_kw = ("интернет", "network", "сеть", "доступ к интернет", "online")
    check_kw = ("проверь", "check", "есть ли", "доступ")
    if engine._has_keywords(normalized, net_kw, fuzzy=True) and engine._has_keywords(normalized, check_kw, fuzzy=True):
        try:
            from modules.network_utils import basic_net_report
            rep = basic_net_report(["api.telegram.org", "gumroad.com", "api.gumroad.com", "google.com"])
            dns = rep.get("dns", {})
            lines = ["Проверка сети:"]
            for host, ok in dns.items():
                lines.append(f"- {host}: {'ok' if ok else 'fail'}")
            lines.append(f"- общий статус: {'online' if rep.get('ok') else 'offline'}")
            if rep.get("seccomp"):
                lines.append(f"- причина блокировки: {rep.get('seccomp')}")
            return {"intent": engine.Intent.QUESTION.value, "response": "\n".join(lines)}
        except Exception:
            return None
    trend_request = engine._has_keywords(normalized, ("тренд", "trends", "trend", "ниш", "niche"), fuzzy=True)
    trend_verb = engine._has_keywords(normalized, ("найд", "скан", "проскан", "проанализ", "подбери", "research"), fuzzy=True)
    deep_request = engine._has_keywords(normalized, ("глубок", "deep", "исследован", "research"), fuzzy=True)
    if deep_request and engine._has_keywords(normalized, ("анализ", "исслед", "research", "разбор"), fuzzy=True):
        topic = engine._extract_research_topic(text)
        actions = [{"action": "run_deep_research", "params": {"topic": topic}}]
        engine._ensure_owner_task_state(text, engine.Intent.SYSTEM_ACTION.value)
        if engine._defer_owner_actions:
            return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Запускаю глубокое исследование по теме: {topic}. Собираю источники и готовлю детальный отчёт.", "actions": actions, "needs_confirmation": False}
        out = await engine._execute_actions(actions)
        return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Запускаю глубокое исследование по теме: {topic}.\n{out or 'Собираю источники и готовлю детальный отчёт.'}", "actions": actions, "needs_confirmation": False}
    if trend_request and trend_verb and engine.agent_registry:
        actions = [{"action": "scan_trends", "params": {}}]
        engine._ensure_owner_task_state(text, engine.Intent.SYSTEM_ACTION.value)
        if engine._defer_owner_actions:
            return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": "Сканирование трендов запущено. Запуск принят, формирую результат.", "actions": actions, "needs_confirmation": False}
        out = await engine._execute_actions(actions)
        return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Сканирование трендов запущено.\n{out or 'Запуск принят, формирую результат.'}", "actions": actions, "needs_confirmation": False}
    analytics_kw = ("аналит", "analytics", "отчет", "отчёт", "report", "dashboard")
    if engine._has_keywords(normalized, analytics_kw, fuzzy=True) and engine.agent_registry:
        try:
            result = await engine.agent_registry.dispatch("analytics", objective=text)
            if result and result.success:
                return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Команда выполнена: аналитика готова.\n[evidence] analytics output: {str(result.output)[:1200]}"}
        except Exception:
            pass
    etsy_kw = ("etsy", "етси", "этси")
    oauth_kw = ("oauth", "pkce", "подключ", "авториз", "логин", "token", "токен")
    if engine._has_keywords(normalized, etsy_kw, fuzzy=True) and engine._has_keywords(normalized, oauth_kw, fuzzy=True):
        try:
            from platforms.etsy import EtsyPlatform
            etsy = EtsyPlatform()
            start = await etsy.start_oauth2_pkce()
            await etsy.close()
            auth_url = start.get("auth_url", "")
            redir = start.get("redirect_uri", "")
            if auth_url:
                return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": "Etsy OAuth подготовлен.\n" f"- auth_url: {auth_url}\n" f"- redirect_uri: {redir}\n" "После авторизации пришли мне code из callback."}
        except Exception:
            pass
    gumroad_kw = ("gumroad", "гумроад", "гамроад")
    sales_kw = ("стат", "statistics", "analytics", "продаж", "revenue", "выручк", "доход")
    if engine._has_keywords(normalized, gumroad_kw, fuzzy=True) and engine._has_keywords(normalized, sales_kw, fuzzy=True):
        live = await engine._quick_gumroad_analytics()
        if live:
            return {"intent": engine.Intent.QUESTION.value, "response": live}
    priority_kw = ("приоритет", "priority")
    goal_kw = ("цели", "goal")
    if engine._has_keywords(normalized, priority_kw, fuzzy=True) and engine._has_keywords(normalized, goal_kw, fuzzy=True):
        m = re.search(r"\b([a-z0-9]{6,40})\b", normalized)
        p = re.search(r"\b(low|medium|high|critical|низк\w*|средн\w*|высок\w*|критич\w*)\b", normalized)
        goal_id = m.group(1) if m else ""
        raw_priority = p.group(1).lower() if p else "high"
        if raw_priority.startswith("low") or raw_priority.startswith("низк"):
            priority = "LOW"
        elif raw_priority.startswith("med") or raw_priority.startswith("сред"):
            priority = "MEDIUM"
        elif raw_priority.startswith("crit") or raw_priority.startswith("крит"):
            priority = "CRITICAL"
        else:
            priority = "HIGH"
        if goal_id:
            engine._ensure_owner_task_state(text, engine.Intent.SYSTEM_ACTION.value)
            out = await engine._execute_actions([{"action": "change_priority", "params": {"goal_id": goal_id, "priority": priority}}])
            return {"intent": engine.Intent.SYSTEM_ACTION.value, "response": f"Изменение приоритета отправлено.\n{out or 'Запрос принят в работу.'}", "actions": [{"action": "change_priority", "params": {"goal_id": goal_id, "priority": priority}}], "needs_confirmation": False}
    err_kw = ("ошибк", "error", "exceptions", "исключен")
    check_kw = ("проверь", "check", "статус", "summary", "сводк")
    system_kw = ("систем", "system")
    if engine._has_keywords(normalized, err_kw, fuzzy=True) and (engine._has_keywords(normalized, check_kw, fuzzy=True) or engine._has_keywords(normalized, system_kw, fuzzy=True)):
        if engine.self_healer and hasattr(engine.self_healer, "get_error_stats"):
            try:
                stats = engine.self_healer.get_error_stats()
                total = int(stats.get("total", 0) or 0)
                resolved = int(stats.get("resolved", 0) or 0)
                unresolved = int(stats.get("unresolved", 0) or 0)
                return {"intent": engine.Intent.QUESTION.value, "response": "Ошибки системы:\n" f"- total: {total}\n" f"- resolved: {resolved}\n" f"- unresolved: {unresolved}"}
            except Exception:
                pass
        return {"intent": engine.Intent.QUESTION.value, "response": "Ошибки системы: модуль self_healer недоступен."}
    return None
