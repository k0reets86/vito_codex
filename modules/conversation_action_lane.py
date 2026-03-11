import asyncio
import json
import time
from typing import Any

from config.settings import settings
from llm_router import TaskType
from modules.owner_preference_model import OwnerPreferenceModel
from modules.prompt_guard import wrap_untrusted_text


async def handle_system_action(engine, text: str) -> dict[str, Any]:
    system_context = engine._format_system_context()
    available_actions = engine._get_available_actions()
    conversation_ctx = engine._format_context()
    owner_focus = engine._owner_task_focus_text()

    lower = text.lower()
    if (
        any(kw in lower for kw in ("printful", "принтфул"))
        and any(kw in lower for kw in ("etsy", "этси", "етси"))
        and engine._looks_like_imperative_request(text)
        and any(kw in lower for kw in ("листинг", "товар", "publish", "опубликуй", "создай"))
    ):
        actions = [{"action": "run_printful_etsy_sync", "params": {"topic": engine._extract_product_topic(text), "auto_publish": True}}]
        if engine._defer_owner_actions:
            return {
                "intent": engine.Intent.SYSTEM_ACTION.value,
                "response": (
                    "Запускаю связку Printful → Etsy (POD pipeline). "
                    "Принял в выполнение."
                ),
                "actions": actions,
                "needs_confirmation": False,
            }
        out = await engine._execute_actions(actions)
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": (
                "Запускаю связку Printful → Etsy (POD pipeline).\n"
                f"{out or 'Принял в выполнение.'}"
            ),
            "actions": actions,
            "needs_confirmation": False,
        }
    platform_key = engine._extract_platform_key(text)
    if platform_key and engine._looks_like_imperative_request(text):
        actions = [{"action": "run_platform_task", "params": {"platform": platform_key, "request": text}}]
        if engine._defer_owner_actions:
            return {
                "intent": engine.Intent.SYSTEM_ACTION.value,
                "response": f"Запускаю задачу на платформе {platform_key}. Принял в выполнение.",
                "actions": actions,
                "needs_confirmation": False,
            }
        out = await engine._execute_actions(actions)
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": f"Запускаю задачу на платформе {platform_key}.\n{out or 'Принял в выполнение.'}",
            "actions": actions,
            "needs_confirmation": False,
        }
    if any(kw in lower for kw in ("amazon", "амазон", "kdp", "кдп")) and any(
        kw in lower for kw in ("заполни", "редакт", "fill", "draft")
    ):
        target_title = engine._extract_target_title(text)
        if target_title:
            actions = [{"action": "run_kdp_draft_maintenance", "params": {"target_title": target_title, "language": "English"}}]
            if engine._defer_owner_actions:
                return {
                    "intent": engine.Intent.SYSTEM_ACTION.value,
                    "response": (
                        f"Запускаю заполнение KDP-драфта: {target_title}. "
                        "Выполняю и проверяю результат."
                    ),
                    "actions": actions,
                    "needs_confirmation": False,
                }
            out = await engine._execute_actions(actions)
            return {
                "intent": engine.Intent.SYSTEM_ACTION.value,
                "response": (
                    f"Запускаю заполнение KDP-драфта: {target_title}.\n"
                    f"{out or 'Выполняю и проверяю результат.'}"
                ),
                "actions": actions,
                "needs_confirmation": False,
            }
    self_improve_keywords = [
        "исправь", "почини", "доработай", "улучши код", "улучши",
        "самоисправ", "добавь интеграц", "сделай интеграц",
        "добавь поддержку", "добавь навык",
    ]
    if any(kw in lower for kw in self_improve_keywords):
        require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": (
                "Запускаю self-improve пайплайн (анализ -> код -> тесты)."
                if not require_confirm
                else "Подтверждаешь запуск self-improve пайплайна (анализ -> код -> тесты)? Ответь: да/нет."
            ),
            "actions": [{"action": "self_improve", "params": {"request": text}}],
            "needs_confirmation": require_confirm,
        }
    trend_request = any(kw in lower for kw in ("тренд", "trends", "trend", "ниш", "niche"))
    trend_verb = any(kw in lower for kw in ("найд", "скан", "проскан", "проанализ", "подбери", "research"))
    if any(kw in lower for kw in ("глубок", "deep research", "deep", "глубокое исслед", "детальный анализ")):
        topic = engine._extract_research_topic(text)
        actions = [{"action": "run_deep_research", "params": {"topic": topic}}]
        if engine._defer_owner_actions:
            return {
                "intent": engine.Intent.SYSTEM_ACTION.value,
                "response": f"Запускаю глубокое исследование: {topic}. Собираю данные и источники.",
                "actions": actions,
                "needs_confirmation": False,
            }
        out = await engine._execute_actions(actions)
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": f"Запускаю глубокое исследование: {topic}.\n{out or 'Собираю данные и источники.'}",
            "actions": actions,
            "needs_confirmation": False,
        }
    if any(kw in lower for kw in ("под ключ", "turnkey", "сделай товар", "создай товар", "запусти продукт", "product pipeline")):
        topic = engine._extract_product_topic(text)
        platforms = engine._extract_platforms(text)
        require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": (
                f"Собираю продукт под ключ: {topic} (платформы: {', '.join(platforms)}). "
                "Сделаю исследование, SEO, контент, юридическую проверку, публикационный пакет и SMM-план."
                if not require_confirm
                else f"Подтверждаешь запуск product pipeline под ключ: {topic} (платформы: {', '.join(platforms)})? да/нет"
            ),
            "actions": [{"action": "run_product_pipeline", "params": {"topic": topic, "platforms": platforms, "auto_publish": False}}],
            "needs_confirmation": require_confirm,
        }
    if any(kw in lower for kw in ("ок публикуй", "publish now", "запускай публикацию", "опубликуй", "публикуй")) and any(
        kw in lower for kw in ("товар", "продукт", "листинг", "gumroad", "etsy", "kofi", "amazon")
    ):
        topic = engine._extract_product_topic(text)
        platforms = engine._extract_platforms(text)
        require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": (
                f"Принял. Запускаю публикацию: {topic} (платформы: {', '.join(platforms)})."
                if not require_confirm
                else f"Подтверждаешь live публикацию: {topic} ({', '.join(platforms)})? да/нет"
            ),
            "actions": [{"action": "run_product_pipeline", "params": {"topic": topic, "platforms": platforms, "auto_publish": True}}],
            "needs_confirmation": require_confirm,
        }
    if any(kw in lower for kw in ("прокач", "улучши себя", "самообуч", "саморазвит", "обнови навыки", "improvement cycle")):
        require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": (
                "Запускаю цикл прокачки: backup -> HR аудит -> research -> self-improve -> безопасная проверка."
                if not require_confirm
                else "Подтверждаешь запуск цикла прокачки (backup -> HR -> research -> self-improve)? да/нет"
            ),
            "actions": [{"action": "run_improvement_cycle", "params": {"request": text}}],
            "needs_confirmation": require_confirm,
        }
    if trend_request and trend_verb:
        actions = [{"action": "scan_trends", "params": {}}]
        if engine._defer_owner_actions:
            return {
                "intent": engine.Intent.SYSTEM_ACTION.value,
                "response": "Запустил скан трендов. Результат формируется, скоро пришлю сводку.",
                "actions": actions,
                "needs_confirmation": False,
            }
        out = await engine._execute_actions(actions)
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": f"Запустил скан трендов.\n{out or 'Результат формируется, скоро пришлю сводку.'}",
            "actions": actions,
            "needs_confirmation": False,
        }
    if any(kw in lower for kw in ["подключи платформ", "добавь платформ", "зарегистрируй платформ", "онбординг платформ"]):
        platform_name = (
            text.replace("подключи", "")
            .replace("зарегистрируй", "")
            .replace("добавь", "")
            .replace("платформу", "")
            .replace("платформы", "")
            .replace("онбординг", "")
            .strip()
        )
        require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": (
                f"Запускаю онбординг платформы '{platform_name or 'unknown'}'."
                if not require_confirm
                else f"Подтверждаешь онбординг платформы '{platform_name or 'unknown'}'? Ответь: да/нет."
            ),
            "actions": [{"action": "onboard_platform", "params": {"platform_name": platform_name}}],
            "needs_confirmation": require_confirm,
        }
    if any(kw in lower for kw in ["изучи сервис", "изучи платформ", "добавь знания", "найди требования"]):
        service = text.replace("изучи", "").replace("платформу", "").replace("сервис", "").strip()
        require_confirm = not bool(getattr(settings, "AUTONOMY_MAX_MODE", False))
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": (
                f"Запускаю изучение сервиса '{service or 'unknown'}' и обновление базы знаний."
                if not require_confirm
                else f"Подтверждаешь изучение сервиса '{service or 'unknown'}' и обновление базы знаний? Ответь: да/нет."
            ),
            "actions": [{"action": "learn_service", "params": {"service": service}}],
            "needs_confirmation": require_confirm,
        }
    if bool(getattr(settings, "AUTONOMY_AUTO_EXECUTE_REQUESTS", False)):
        return {
            "intent": engine.Intent.SYSTEM_ACTION.value,
            "response": "Принял задачу. Выполняю автономно: сначала попробую существующими навыками, при необходимости доучусь и повторю.",
            "actions": [{"action": "autonomous_execute", "params": {"request": text}}],
            "needs_confirmation": False,
        }

    prompt = (
        f"{engine.VITO_PERSONALITY}\n\n"
        f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
        f"{engine._build_operational_memory_context(text, include_errors=True)}\n\n"
        f"{owner_focus}\n\n"
        f"История разговора:\n{conversation_ctx}\n\n"
        f"Доступные действия:\n{available_actions}\n\n"
        f"Владелец просит: \"{wrap_untrusted_text(text)}\"\n\n"
        f"Определи какие действия нужно выполнить и дай подтверждение.\n"
        f"Ответь в JSON:\n"
        f'{{"response": "текст ответа владельцу", "actions": [{{"action": "имя_действия", "params": {{...}}}}]}}\n\n'
        f"Если действие не нужно — actions: []"
    )

    response = await engine.llm_router.call_llm(
        task_type=TaskType.ROUTINE,
        prompt=prompt,
        estimated_tokens=500,
    )

    actions = []
    reply = f"Принял: {text[:80]}"

    if response:
        try:
            parsed = engine._extract_json(response)
            if parsed:
                reply = parsed.get("response", reply)
                actions = parsed.get("actions", [])
        except Exception:
            reply = response
    if not actions and engine._looks_like_imperative_request(text):
        low = text.lower()
        if any(k in low for k in ("amazon", "амазон", "kdp", "кдп")) and any(
            k in low for k in ("удали", "удалить", "редакт", "заполни", "draft", "книг")
        ):
            return {
                "intent": engine.Intent.SYSTEM_ACTION.value,
                "response": (
                    "Понял задачу по KDP. Сейчас у меня автоматизированы: вход и инвентаризация. "
                    "Удаление/полное редактирование драфтов в безопасном контуре ещё не подключено, "
                    "поэтому не буду имитировать выполнение."
                ),
                "actions": [],
                "needs_confirmation": False,
            }
        actions = [{"action": "autonomous_execute", "params": {"request": text}}]
        reply = "Принял задачу. Запускаю выполнение и вернусь с конкретным результатом."
    if "вот план" in str(reply).lower() and "думаешь" in str(reply).lower():
        reply = "Принял. Запускаю выполнение и вернусь с результатом."
    risky_actions = {"apply_code_change"}
    needs_confirmation = any(
        str(a.get("action", "")).strip() in risky_actions
        for a in actions
        if isinstance(a, dict)
    )
    if actions and needs_confirmation:
        reply = f"{reply}\nПодтверди выполнение: да/нет."

    return {
        "intent": engine.Intent.SYSTEM_ACTION.value,
        "response": reply,
        "actions": actions,
        "needs_confirmation": needs_confirmation,
    }


async def handle_goal_request(engine, text: str) -> dict[str, Any]:
    system_context = engine._format_system_context()
    conversation_ctx = engine._format_context()
    owner_focus = engine._owner_task_focus_text()

    skills_context = ""
    owner_prefs = ""
    if engine.memory:
        try:
            skills = engine.memory.search_skills(text, limit=3)
            if skills:
                skills_context = "\nНавыки: " + ", ".join(s["name"] for s in skills)
        except Exception:
            pass
        try:
            prefs = engine.memory.search_knowledge("owner preference", n_results=3)
            if prefs:
                owner_prefs = "\nПредпочтения владельца:\n" + "\n".join(
                    f"- {p['text'][:150]}" for p in prefs
                )
        except Exception:
            pass
        try:
            model = OwnerPreferenceModel()
            pref_rows = model.list_preferences(limit=5)
            if pref_rows:
                lines = []
                keys = []
                for pr in pref_rows:
                    conf = float(pr.get("confidence", 0))
                    val = pr.get("value")
                    key = pr.get("pref_key")
                    keys.append(key)
                    lines.append(f"- {key}: {val} (conf={conf:.2f})")
                owner_prefs = owner_prefs + "\n" + "\n".join(lines) if owner_prefs else "\nПредпочтения владельца:\n" + "\n".join(lines)
                try:
                    from modules.data_lake import DataLake
                    DataLake().record(
                        agent="conversation_engine",
                        task_type="owner_prefs_used",
                        status="success",
                        output={"keys": keys},
                        source="system",
                    )
                except Exception:
                    pass
        except Exception:
            pass
    hot_memory_ctx = engine._build_operational_memory_context(text, include_errors=True)

    auto_approve = bool(getattr(settings, "OWNER_AUTO_APPROVE_GOALS", True))
    approval_hint = (
        "2. Можно начинать сразу и выдать первый результат без дополнительного подтверждения\n"
        if auto_approve
        else "2. НЕ начинай сразу. Сформируй план и предложи на одобрение\n"
    )
    prompt = (
        f"{engine.VITO_PERSONALITY}\n\n"
        f"=== СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n=== КОНЕЦ ===\n\n"
        f"{hot_memory_ctx}\n\n"
        f"{owner_focus}\n\n"
        f"История разговора:\n{conversation_ctx}\n\n"
        f"{skills_context}{owner_prefs}\n\n"
        f"Владелец просит: \"{wrap_untrusted_text(text)}\"\n\n"
        f"ПРАВИЛА:\n"
        f"1. Все продукты/контент — на АНГЛИЙСКОМ (US/CA/EU market)\n"
        f"{approval_hint}"
        f"3. Если что-то неясно — задай вопрос владельцу (на русском)\n"
        f"4. План должен завершаться конкретным результатом: файл, ссылка, публикация\n\n"
        f"Доступные инструменты:\n"
        f"- 23 агента (content_creator, smm_agent, research_agent, browser_agent и др.)\n"
        f"- Платформы: Gumroad, Printful, Twitter\n"
        f"- Генерация изображений: Replicate, BFL, WaveSpeed, DALL-E\n"
        f"- CodeGenerator: может дописать код VITO\n"
        f"- BrowserAgent: может зарегистрироваться на сайтах, заполнять формы\n\n"
        f"Ответь JSON:\n"
        f'{{"goal_title": "краткое название (English)", '
        f'"goal_description": "план 5-7 шагов (English content, but plan itself in Russian for owner)", '
        f'"confirmation": "кратко и по-человечески на русском: принял задачу и начинаю выполнение", '
        f'"needs_approval": {str(not auto_approve).lower()}, '
        f'"estimated_cost_usd": 0.05, '
        f'"priority": "HIGH"}}'
    )

    response = await engine.llm_router.call_llm(
        task_type=TaskType.ROUTINE,
        prompt=prompt,
        estimated_tokens=600,
    )

    goal_title = text[:100]
    goal_description = text
    confirmation = (
        f"Принял задачу: \"{goal_title}\"\n\nНачинаю выполнение и отправлю полный отчёт."
        if auto_approve
        else f"Принял задачу: \"{goal_title}\"\n\nГотовлю план. Отправлю на одобрение."
    )
    priority = "HIGH"
    needs_approval = not auto_approve
    estimated_cost = 0.05

    if response:
        try:
            data = engine._extract_json(response)
            if data:
                goal_title = data.get("goal_title", goal_title)
                goal_description = data.get("goal_description", text)
                confirmation = data.get("confirmation", confirmation)
                priority = data.get("priority", "HIGH")
                needs_approval = data.get("needs_approval", not auto_approve)
                estimated_cost = data.get("estimated_cost_usd", 0.05)
        except Exception:
            pass
    if auto_approve:
        needs_approval = False

    return {
        "intent": engine.Intent.GOAL_REQUEST.value,
        "response": confirmation,
        "create_goal": True,
        "goal_title": goal_title,
        "goal_description": goal_description,
        "goal_priority": priority,
        "needs_approval": needs_approval,
        "estimated_cost_usd": estimated_cost,
    }


async def execute_actions(engine, actions: list[dict]) -> str:
    results = []
    allowed = engine._allowed_actions()
    for act in actions[:3]:
        action_name = act.get("action", "")
        params = act.get("params", {})
        try:
            if action_name not in allowed:
                results.append(f"Действие '{action_name}' недоступно по политике безопасности.")
                continue
            if action_name == "apply_code_change":
                if not engine.comms:
                    results.append("Не могу изменить код: канал подтверждения недоступен.")
                    continue
                target = params.get("file", "")
                instruction = params.get("instruction", "")
                approved = await engine.comms.request_approval(
                    request_id=f"code_change_{int(time.time())}",
                    message=(
                        "[conversation_engine] Запрос изменения кода.\n"
                        "Подтверди ✅ или отклони ❌.\n"
                        f"Файл: {target}\n"
                        f"Инструкция: {instruction[:300]}"
                    ),
                    timeout_seconds=3600,
                )
                if approved is not True:
                    results.append("Изменение кода отменено: подтверждение не получено.")
                    continue
            result = await engine._dispatch_action(action_name, params)
            if result:
                results.append(str(result))
            else:
                results.append(f"Действие '{action_name}' выполнено.")
        except Exception as e:
            results.append(f"Ошибка при выполнении '{action_name}': {e}")
            engine.logger.warning(f"Action error {action_name}: {e}", extra={"event": "action_error"})
    return "\n".join(results) if results else ""


async def dispatch_action(engine, action: str, params: dict) -> str:
    method = getattr(engine, "_dispatch_action_legacy", None)
    if method is None:
        raise RuntimeError("conversation dispatch legacy implementation missing")
    return await method(action, params)
