import json


def is_status_prompt(text: str) -> bool:
    s = str(text or "").strip().lower()
    return any(
        token in s
        for token in (
            "статус",
            "status",
            "состояние аккаунта",
            "состояние",
            "state",
            "проверь аккаунт",
            "покажи аккаунт",
            "проверка входа",
            "авториз",
            "логин",
        )
    )


def is_inventory_prompt(text: str) -> bool:
    s = str(text or "").strip().lower()
    if not s:
        return False
    if any(
        x in s
        for x in (
            "создай",
            "создать",
            "собери",
            "собрать",
            "опубликуй",
            "опубликовать",
            "размести",
            "разместить",
            "заполни",
            "заполнить",
            "сгенерируй",
            "сделай",
            "make",
            "create",
            "publish",
            "post ",
        )
    ):
        return False
    if any(x in s for x in ("соцпак", "соц пак", "social pack", "social", "пинтерест", "pinterest", "твиттер", "twitter", "reddit", "реддит")):
        return False
    if any(x in s for x in ("тренд", "trend", "ниш", "niche", "конкурент", "рынок")):
        return False
    if any(x in s for x in ("профиль", "profile")) and any(x in s for x in ("настрой", "settings")):
        return False
    return any(
        token in s
        for token in (
            "аккаунт",
            "account",
            "кабинет",
            "профиль",
            "товар",
            "товары",
            "продукт",
            "продукты",
            "листинг",
            "листинги",
            "каталог",
            "ассортимент",
            "products",
            "listings",
            "inventory",
        )
    )


def detect_contextual_service_status_request(agent, text: str) -> str:
    s = str(text or "").strip().lower()
    if not s or not is_status_prompt(s):
        return ""
    explicit = agent._detect_service_from_text(s)
    if explicit:
        return explicit
    if any(x in s for x in ("vito", "вито", "система", "system")):
        return ""
    if agent._has_fresh_service_context():
        return agent._last_service_context
    if agent._pending_service_auth:
        try:
            return next(reversed(agent._pending_service_auth))
        except Exception:
            return ""
    return ""


def detect_contextual_service_inventory_request(agent, text: str) -> str:
    s = str(text or "").strip().lower()
    if not s or not is_inventory_prompt(s):
        return ""
    if any(
        x in s
        for x in (
            "выбери",
            "предлож",
            "структур",
            "идея",
            "вариант",
            "концеп",
            "упаков",
            "план",
        )
    ):
        return ""
    explicit = agent._detect_service_from_text(s)
    if explicit:
        return explicit
    if any(x in s for x in ("vito", "вито", "система", "system")):
        return ""
    if agent._has_fresh_service_context():
        return agent._last_service_context
    if agent._pending_service_auth:
        try:
            return next(reversed(agent._pending_service_auth))
        except Exception:
            return ""
    return ""


def detect_service_from_reply_context(agent, reply_meta: dict[str, str] | None) -> str:
    if not isinstance(reply_meta, dict):
        return ""
    text = str(reply_meta.get("text", "") or "").strip()
    if not text:
        return ""
    return agent._detect_service_from_text(text)


def format_service_auth_status(agent, service: str) -> str:
    svc = str(service or "").strip().lower()
    if not svc:
        return "Не понял, по какому сервису показать статус."
    title, auth_url = agent._service_auth_meta(svc)
    if svc in agent._pending_service_auth:
        return (
            f"{title}: ожидается подтверждение входа.\n"
            f"Ссылка: {auth_url}\n"
            "После входа нажми «Я вошел» или напиши «готово»."
        )
    if agent._service_auth_confirmed.get(svc):
        return f"{title}: вход подтверждён. Повторный логин сейчас не требуется."
    return f"{title}: вход пока не подтверждён. Напиши «зайди на {title}» для авторизации."


async def format_service_auth_status_live(agent, service: str) -> str:
    svc = str(service or "").strip().lower()
    base = format_service_auth_status(agent, svc)
    if not svc:
        return base
    title, _ = agent._service_auth_meta(svc)
    if svc in agent._pending_service_auth:
        return base

    if svc == "amazon_kdp":
        try:
            probe_rc, _ = await agent._run_kdp_probe_stable()
            if probe_rc == 0:
                agent._mark_service_auth_confirmed(svc)
                return f"{title}: подключение активно (live-check OK). Повторный логин не требуется."
            if agent._service_auth_confirmed.get(svc):
                return (
                    f"{title}: вход ранее подтверждён, но live-check сейчас не прошёл. "
                    "Если действия в Amazon не выполняются, запусти вход заново."
                )
            return f"{title}: live-check не подтвердил сессию. Нужна авторизация: зайди на {title}."
        except Exception:
            return (
                f"{title}: статус по кэшу — вход ранее подтверждён, но live-check сейчас недоступен."
                if agent._service_auth_confirmed.get(svc)
                else f"{title}: вход пока не подтверждён."
            )

    if agent._requires_strict_auth_verification(svc):
        try:
            ok, detail = await agent._verify_service_auth(svc)
            if ok:
                agent._mark_service_auth_confirmed(svc)
                return f"{title}: подключение активно (live-check OK). Повторный логин не требуется."
            has_storage, _ = agent._has_cookie_storage_state(svc)
            if has_storage and agent._service_auth_confirmed.get(svc):
                return (
                    f"{title}: есть сохранённая browser-сессия, но прямой live-check сейчас не прошёл. "
                    "Если действие не выполняется, запусти вход заново."
                )
            agent._clear_service_auth_confirmed(svc)
            return f"{title}: вход не подтверждён (live-check fail). {detail}"
        except Exception as e:
            agent._clear_service_auth_confirmed(svc)
            return f"{title}: вход не подтверждён. Ошибка проверки: {e}"

    return base


async def format_service_inventory_snapshot(agent, service: str) -> str:
    svc = str(service or "").strip().lower()
    if not svc:
        return "Не понял, по какому сервису проверить товары."
    title, _ = agent._service_auth_meta(svc)

    if svc == "amazon_kdp":
        try:
            probe_rc, _ = await agent._run_kdp_probe_stable()
            if probe_rc != 0:
                return (
                    f"{title}: не вижу активной сессии аккаунта (live-check не пройден). "
                    "Сначала зайди в аккаунт, потом повтори проверку товаров."
                )
        except Exception:
            pass
        try:
            inv_rc, inv_out = await agent._run_kdp_inventory_probe()
            if inv_rc == 0:
                payload_line = ""
                for ln in reversed((inv_out or "").splitlines()):
                    ln = ln.strip()
                    if ln.startswith("{") and ln.endswith("}"):
                        payload_line = ln
                        break
                if payload_line:
                    data = json.loads(payload_line)
                    if bool(data.get("ok", False)):
                        items = data.get("items") or []
                        if isinstance(items, list):
                            noise = (
                                "how would you rate your experience",
                                "visit our help center",
                                "thank you for your feedback",
                            )
                            cleaned = []
                            seen = set()
                            for it in items:
                                t = str(it or "").strip()
                                if not t:
                                    continue
                                low = t.lower()
                                if any(n in low for n in noise):
                                    continue
                                if low in seen:
                                    continue
                                seen.add(low)
                                cleaned.append(t)
                            items = cleaned
                        count = int(data.get("products_count", 0) or 0)
                        if isinstance(items, list):
                            count = len(items)
                        lines = [f"{title}: состояние аккаунта", f"- Товаров/книг: {count}"]
                        if items:
                            lines.append("- Примеры:")
                            for it in items[:5]:
                                lines.append(f"  - {str(it)[:120]}")
                        return "\n".join(lines)
        except Exception:
            pass

    if not agent._agent_registry:
        return f"{title}: модуль проверки товаров не подключён."
    try:
        result = await agent._agent_registry.dispatch("sales_check", platform=svc)
    except Exception as e:
        return f"{title}: ошибка запроса данных аккаунта: {e}"

    if not result or not getattr(result, "success", False):
        return f"{title}: не удалось получить данные аккаунта."
    payload = getattr(result, "output", {}) or {}
    data = payload.get(svc, payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return f"{title}: данные аккаунта получены в неподдерживаемом формате."
    if data.get("error"):
        return f"{title}: проверка аккаунта вернула ошибку: {data.get('error')}"

    lines = [f"{title}: состояние аккаунта"]
    has_metrics = False

    for key, label in (
        ("products_count", "Товаров"),
        ("listings", "Листингов"),
        ("sales", "Продаж"),
        ("orders", "Заказов"),
        ("total_views", "Просмотров"),
        ("total_favorites", "Добавили в избранное"),
    ):
        if key in data:
            lines.append(f"- {label}: {data.get(key)}")
            has_metrics = True
    if "revenue" in data:
        try:
            lines.append(f"- Выручка: ${float(data.get('revenue') or 0.0):.2f}")
        except Exception:
            lines.append(f"- Выручка: {data.get('revenue')}")
        has_metrics = True

    if not has_metrics:
        if data.get("raw_data"):
            lines.append("- Детальные данные получены, но формат неструктурирован.")
        else:
            lines.append("- Метрики товаров не вернулись. Возможно, у аккаунта нет доступных данных через текущий канал.")

    return "\n".join(lines)
