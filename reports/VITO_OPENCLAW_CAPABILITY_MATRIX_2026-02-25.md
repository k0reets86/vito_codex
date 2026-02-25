# VITO vs OpenClaw Capability Matrix (2026-02-25)

Статусы:
- `FULL` — есть рабочий контур и тестируемый функционал
- `PARTIAL` — есть архитектура/модуль, но не закрыт полный E2E
- `GAP` — минимальная или отсутствующая реализация

| # | Группа OpenClaw | Статус VITO | Комментарий |
|---|---|---|---|
| 1 | Разработка и программирование | FULL | Codex/self-heal/self-updater/pytest контур |
| 2 | Git и GitHub | FULL | git workflows есть, но автопроцессы ограничены политиками |
| 3 | Соцсеть агентов | PARTIAL | A2A/registry есть, отдельной social-сети нет |
| 4 | Веб и фронтенд | PARTIAL | browser/publisher/dashboard есть, неполный набор стеков |
| 5 | DevOps и облака | FULL | service/watchdog/backup/recovery |
| 6 | Автоматизация браузера | FULL | browser_agent + playwright pipeline |
| 7 | Генерация изображений/видео | PARTIAL | image pipeline есть, видео-контур ограничен |
| 8 | Экосистема Apple | PARTIAL | отдельные интеграции не закрыты |
| 9 | Поиск и исследования | FULL | trend/research/rss/reddit/knowledge |
| 10 | Инструменты оркестратора | FULL | memory/cost/context/security guards |
| 11 | CLI-утилиты | FULL | shell/devops/diagnostics |
| 12 | Маркетинг и продажи | PARTIAL | стратегии есть, E2E на платформах частично |
| 13 | Продуктивность и задачи | PARTIAL | goals/schedules, но внешний PM-stack частичный |
| 14 | ИИ и модели | FULL | multi-router, policy-report, brainstorm |
| 15 | Данные и аналитика | FULL | data_lake + KPI + trend |
| 16 | Финансы | PARTIAL | spend/budget есть, расширенный finance stack частичный |
| 17 | Медиа и стриминг | PARTIAL | YouTube/контент частично |
| 18 | Заметки и знания | PARTIAL | memory+KB есть, внешние PKM интеграции частичные |
| 19 | iOS/macOS dev | GAP | нет full pipeline |
| 20 | Транспорт | GAP | нет full pipeline |
| 21 | Личное развитие | GAP | нет full pipeline |
| 22 | Здоровье и фитнес | GAP | нет full pipeline |
| 23 | Коммуникации | FULL | Telegram + owner inbox fallback |
| 24 | STT/TTS | PARTIAL | базовые заготовки, нет полного voice pipeline |
| 25 | Smart Home/IoT | GAP | нет full pipeline |
| 26 | E-commerce | PARTIAL | Gumroad/etsy/printful контур неполный E2E |
| 27 | Календарь и планирование | FULL | schedule manager + natural updates |
| 28 | PDF и документы | FULL | document agent + OCR/PDF pipeline |
| 29 | Self-hosted и автоматизация | PARTIAL | есть основа, неполный catalog |
| 30 | Безопасность и пароли | PARTIAL | guards есть, enterprise hardening не полный |
| 31 | Игры | GAP | нет full pipeline |
| 32 | Агент-агент протоколы | PARTIAL | registry/dispatch есть, формальные протоколы частичны |

## Приоритет закрытия GAP (к 10/10)
1. #26 E-commerce: довести 3–5 платформ E2E с evidence.
2. #30 Security: hardening и policy enforcement end-to-end.
3. #24 Voice: базовый STT/TTS production pipeline.
4. #19/#25: capability-packs (минимальные, но рабочие).
