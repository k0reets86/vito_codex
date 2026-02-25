# Аудит файловой системы VITO (без удаления)

## Контекст
- Хост: `/home/vito`
- Проект: `/home/vito/vito-agent`
- Режим: только анализ, **ничего не удалялось**

## Что проверено
- Полный обход файлов (`find`), всего файлов: **44,766**
- Размеры директорий (`du`)
- Крупные файлы
- Паттерны мусора (`<MagicMock...>`, `__pycache__`, `.pytest_cache`)
- Root-owned файлы в проекте
- Git-статус

## Ключевые цифры
- `/home/vito` общий объём: ~**3.5G**
- `/home/vito/vito-agent`: ~**1.6G**
- `/home/vito/vito-agent/backups`: **1.6G**
- `/home/vito/vito-agent/output`: **27M**
- `/home/vito/vito-agent/logs`: **9.5M**
- `/home/vito/vito-agent/memory`: **7.2M**

## Наибольшие файлы
- `/home/vito/vito-agent/backups/manual_before_gumroad_20260224_091542.tgz` — **~820MB**
- `/home/vito/vito-agent/backups/manual_before_gumroad_20260224_091626.tgz` — **~28MB**
- `/home/vito/vito-agent/logs/vito.log` — **~7.8MB**
- Много дубликатов больших логов/скриншотов внутри `backups/`

## Признаки мусора
- В корне проекта директорий `'<MagicMock ...>'`: **117**
- В `backups/` таких директорий: **699**
- Причина: следы тестов/моков, попавшие в файловую систему
- Есть также `MagicMock/` директория

## Root-owned объекты в проекте
- Найдено root-owned путей: **34**
- Примеры:
  - `/home/vito/vito-agent/.claude/settings.local.json`
  - `/home/vito/vito-agent/vito_agent_prompts.md`
  - часть файлов в `output/articles`, `output/social`
  - ряд старых бэкапов
- Риск: периодические `Permission denied` при правках/коммитах

## Git-состояние
- Ветка `main` отслеживает `origin/main`
- Есть изменённый файл: `docs/OWNER_REQUIREMENTS_LOG.md`
- Наличие неотслеживаемого мусора было связано с `<MagicMock...>` каталогами; для части добавлены ignore-правила

## Вывод
- Основной объём и «мусорность» сосредоточены в `backups/` и артефактах тестов (`<MagicMock...>`)
- Критичных повреждений проекта не обнаружено
- Система рабочая, но нужна санитарная чистка по правилам (безопасно и поэтапно)

## Безопасный план очистки (без удаления в этом аудите)
1. Согласовать retention-политику для `backups/` (например, 7/30 дней + keep latest N).
2. Удалить `'<MagicMock...>'` и `MagicMock/` в проекте и бэкапах (после отдельного подтверждения).
3. Исправить владельцев root-owned файлов в `vito-agent` на `vito:vito`.
4. Включить ротацию логов для `logs/*.log`.
5. Расширить `.gitignore` паттернами для мок-артефактов и временных директорий.
6. Повторный аудит после чистки и сверка размера.

