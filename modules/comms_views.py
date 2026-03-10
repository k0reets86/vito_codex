"""Reusable Telegram-facing text/render helpers for CommsAgent."""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def help_catalog() -> dict[str, Any]:
    return {
        "daily": [
            ("status", "Короткий статус VITO"),
            ("goals", "Активные цели"),
            ("goal <текст>", "Создать новую цель"),
            ("report", "Сводка: цели + финансы"),
            ("spend", "Лимит и траты за сегодня"),
            ("approve", "Одобрить ожидающий запрос"),
            ("reject", "Отклонить ожидающий запрос"),
            ("task_current", "Показать текущую owner-задачу"),
            ("task_done", "Отметить текущую задачу как выполненную"),
            ("balances", "Проверить балансы сервисов"),
        ],
        "rare": [
            ("tasks", "Задачи в выполнении"),
            ("goals_all", "История целей"),
            ("trends", "Сканер трендов"),
            ("earnings", "Доходы за 7 дней"),
            ("pubq", "Очередь публикаций"),
            ("pubrun", "Принудительно прогнать очередь публикаций"),
            ("workflow", "Состояние workflow"),
            ("handoffs", "Трассировка handoff событий"),
            ("prefs", "Предпочтения владельца"),
            ("packs", "Capability packs"),
            ("llm_mode free|prod|status", "Переключить профиль LLM"),
        ],
        "system": [
            ("cancel", "Пауза/отмена текущих задач"),
            ("resume", "Продолжить после паузы"),
            ("stop yes", "Остановить Decision Loop (с подтверждением)"),
            ("health", "Статистика SelfHealer/здоровья"),
            ("errors", "Последние ошибки"),
            ("logs", "Последние строки логов"),
            ("backup", "Сделать бэкап кода"),
            ("rollback", "Откатить последний апдейт"),
            ("clear_goals yes", "Очистить все цели (опасно)"),
            ("nettest", "Проверка сети и DNS"),
        ],
        "commands": {
            "status": ("Текущий статус ядра, бюджета и задач.", "Когда нужно понять, жив ли контур."),
            "goals": ("Показывает активные цели.", "Быстрый контроль очереди работ."),
            "goal": ("Создаёт новую цель.", "Используй: /goal <что сделать>."),
            "report": ("Сводный отчёт по системе.", "Когда нужен полный срез в одном сообщении."),
            "spend": ("Дневной расход LLM.", "Контроль токенов и бюджета."),
            "approve": ("Одобряет pending approval.", "Только если уверен в действии."),
            "reject": ("Отклоняет pending approval.", "Безопасно отклонять сомнительные запросы."),
            "cancel": ("Ставит выполнение на паузу.", "Когда нужно мгновенно остановить активность."),
            "resume": ("Возобновляет выполнение.", "После /cancel."),
            "health": ("Показывает состояние self-healing.", "Для диагностики стабильности."),
            "logs": ("Выводит последние строки логов.", "Для быстрого поиска причины ошибки."),
            "backup": ("Делает резервную копию.", "Перед рискованными изменениями."),
            "rollback": ("Откат к последнему бэкапу.", "Если последняя доработка сломала поведение."),
            "clear_goals": ("Удаляет все цели.", "Использовать только осознанно."),
            "llm_mode": ("Меняет профиль маршрутизации LLM.", "free для тестов на Gemini, prod для боевого распределения."),
        },
    }


def render_help(topic: str | None = None) -> str:
    topic_norm = str(topic or "").strip().lower()
    catalog = help_catalog()

    if topic_norm in {"daily", "day", "ежедневные", "daily_commands"}:
        lines = ["Ежедневные команды (часто используемые):"]
        lines.extend([f"/{cmd} — {desc}" for cmd, desc in catalog["daily"]])
        return "\n".join(lines)
    if topic_norm in {"rare", "редкие", "ops"}:
        lines = ["Редкие команды (по ситуации):"]
        lines.extend([f"/{cmd} — {desc}" for cmd, desc in catalog["rare"]])
        return "\n".join(lines)
    if topic_norm in {"system", "sys", "системные", "danger"}:
        lines = ["Системные/осторожные команды:"]
        lines.extend([f"/{cmd} — {desc}" for cmd, desc in catalog["system"]])
        lines.append("Совет: для рискованных команд сначала делай /backup.")
        return "\n".join(lines)

    cmd_key = topic_norm.lstrip("/")
    cmd_info = catalog["commands"].get(cmd_key)
    if cmd_info:
        what, when = cmd_info
        return f"/{cmd_key}\nЧто делает: {what}\nКогда использовать: {when}"

    return (
        "Справка по командам VITO\n\n"
        "Разделы:\n"
        "/help_daily — ежедневные команды\n"
        "/help_rare — редкие команды\n"
        "/help_system — системные/осторожные\n\n"
        "Точечно по команде:\n"
        "/help status\n"
        "/help goal\n"
        "/help backup\n\n"
        "Быстрый старт:\n"
        "1) /status\n"
        "2) /goals\n"
        "3) /goal <что сделать>\n"
        "4) /approve или /reject"
    )


def help_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Ежедневные", callback_data="help_topic:daily"),
                InlineKeyboardButton("Редкие", callback_data="help_topic:rare"),
            ],
            [InlineKeyboardButton("Системные", callback_data="help_topic:system")],
        ]
    )


def render_auth_hub() -> str:
    return (
        "Входы в сервисы\n"
        "- Поддержка: Amazon KDP, Etsy, Gumroad, Printful\n"
        "- Соцсети: X/Twitter, Reddit, Threads, Instagram, Facebook, TikTok, Pinterest, YouTube, LinkedIn\n"
        "- Прочее: WordPress, Medium\n"
        "- Любой сайт: 'зайди на https://site.com' или 'зайди на site.com'\n\n"
        "После входа нажми «Я вошел» или напиши «готово»."
    )


def render_more_menu() -> str:
    return (
        "Дополнительно\n"
        "- Исследование: «проведи глубокое исследование ...» или кнопка/текст «Исследовать»\n"
        "- Платформы: «изучи сервис <название>» или текст «Платформы»\n"
        "- /spend — расходы\n"
        "- /help — справка\n"
        "- /logs — логи\n"
        "- /health — здоровье\n"
        "- /balances — балансы"
    )


def render_research_hub() -> str:
    return (
        "Исследование\n"
        "- Напиши: «проведи глубокое исследование ниши цифровых товаров»\n"
        "- Или: «исследуй платформу substack»\n"
        "- После выбора варианта можно ответить просто цифрой: `1`, `2`, `3`\n"
        "- Потом: «создавай на etsy/gumroad/kdp»"
    )


def render_create_hub() -> str:
    return (
        "Создание\n"
        "- Напиши: «создавай на etsy»\n"
        "- Или: «создай товар на gumroad»\n"
        "- Для соцпакета: «собери соцпакет для товара»\n"
        "- Если задача уже выбрана, VITO продолжит по текущему контексту"
    )



def render_platform_readiness_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- Готовность платформ: нет данных"
    owner_grade = sum(1 for x in items if str(x.get("owner_grade_state") or "") == "owner_grade")
    ready_now = sum(1 for x in items if bool(x.get("can_validate_now")))
    blocked = sum(1 for x in items if str(x.get("blocker") or "").strip())
    lines = [
        f"- Готовность платформ: owner-grade={owner_grade}, можно валидировать сейчас={ready_now}, блокеры={blocked}"
    ]
    for item in items[:5]:
        svc = str(item.get("service") or "?")
        state = str(item.get("owner_grade_state") or "unknown")
        blocker = str(item.get("blocker") or "")
        suffix = f" | blocker={blocker}" if blocker else ""
        lines.append(f"  - {svc}: {state}{suffix}")
    return "\n".join(lines)


def render_platforms_hub() -> str:
    return (
        "Платформы\n"
        "- Листинги: Etsy, Gumroad, Amazon KDP, Ko-fi\n"
        "- Связки: Printful -> Etsy\n"
        "- Соцсети: X, Pinterest, Reddit\n"
        "- Для онбординга новой платформы: «изучи сервис <название>»"
    )
