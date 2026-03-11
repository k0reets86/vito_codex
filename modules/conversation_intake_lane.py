from __future__ import annotations

import re
import time
from typing import Any

from config.settings import settings
from llm_router import TaskType


async def maybe_handle_fast_url_route(engine, text: str) -> dict[str, Any] | None:
    url = engine._extract_url(text)
    if url and engine.agent_registry and settings.BROWSER_DEFAULT_ON_URL:
        try:
            lower = text.lower()
            if any(k in lower for k in ("скрин", "снимок", "screenshot", "screen")):
                task_type = "screenshot"
                path = f"/tmp/vito_browse_{int(time.time())}.png"
                result = await engine.agent_registry.dispatch(task_type, url=url, path=path)
                if result and result.success:
                    actual_path = path
                    if isinstance(result.output, dict) and result.output.get("path"):
                        actual_path = result.output["path"]
                    return {
                        "response": f"Открыл страницу. Скриншот готов.\n📎 {actual_path}",
                        "intent": engine.Intent.QUESTION.value,
                    }
            if any(k in lower for k in ("текст", "прочитай", "extract", "вытащи", "что написано")):
                result = await engine.agent_registry.dispatch("web_scrape", url=url, selector="body")
                if result and result.success:
                    return {
                        "response": f"Текст со страницы:\n{str(result.output)[:3500]}",
                        "intent": engine.Intent.QUESTION.value,
                    }
            result = await engine.agent_registry.dispatch("browse", url=url)
            if result and result.success:
                out = result.output or {}
                title = out.get("title", "")
                status = out.get("status", "")
                return {"response": f"Страница открыта. {title} (HTTP {status})", "intent": engine.Intent.QUESTION.value}
        except Exception:
            pass

    if "http://" in text or "https://" in text:
        try:
            from modules.web_fetch import fetch_url

            m = re.search(r"https?://\S+", text)
            if m:
                url = m.group(0).rstrip(".,)")
                data = fetch_url(url)
                response = f"URL: {url}\nTitle: {data.get('title','')}\n\n{data.get('text','')}"
                return {"response": response, "intent": engine.Intent.QUESTION.value}
        except Exception:
            pass
    return None


def bootstrap_owner_turn(engine, text: str, intent, tones) -> None:
    engine._add_turn("user", text, intent)
    if engine.owner_task_state and intent in (engine.Intent.GOAL_REQUEST, engine.Intent.SYSTEM_ACTION):
        try:
            active_before = engine.owner_task_state.get_active()
            saved = engine.owner_task_state.set_active(text=text, source="telegram", intent=intent.value, force=False)
            if active_before and not saved:
                pass
        except Exception:
            pass

    if intent in (engine.Intent.GOAL_REQUEST, engine.Intent.QUESTION, engine.Intent.SYSTEM_ACTION) and engine.memory:
        try:
            engine.memory.store_knowledge(
                doc_id=f"user_msg_{int(time.time())}",
                text=f"Владелец: {text}",
                metadata={"type": "user_request", "intent": intent.value, "tones": tones},
            )
        except Exception:
            pass


def ensure_owner_task_state(engine, text: str, intent_value: str | None) -> None:
    if not engine.owner_task_state:
        return
    try:
        active_before = engine.owner_task_state.get_active()
        intent_str = str(intent_value or "").strip().lower()
        if intent_str not in {engine.Intent.GOAL_REQUEST.value, engine.Intent.SYSTEM_ACTION.value}:
            return
        saved = engine.owner_task_state.set_active(
            text=text,
            source="telegram",
            intent=intent_str,
            force=False,
        )
        if active_before and not saved:
            return
    except Exception:
        return


def owner_friendly_action_results(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return "Принял задачу в работу. Дам краткий прогресс и вернусь с результатом."
    low = s.lower()
    noisy = ("task_id", "goal_id", "trace_id", "session_id", "{", "}", "[", "]")
    if any(tok in low for tok in noisy):
        return "Принял задачу в работу. Иду выполнять, вернусь с прогрессом и итогом."
    return s
