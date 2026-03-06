# VITO Reproducible Setup

Цель: забрать репозиторий и поднять VITO на новом сервере без ручного поиска скрытых зависимостей.

## Что нужно перенести
- весь репозиторий
- `.env` или заполненный `.env.example`
- содержимое `runtime/` только если нужны текущие browser/storage sessions
- содержимое `memory/` только если нужно перенести накопленную память/Chroma/SQLite

## Быстрый Docker-старт
1. Скопировать проект на сервер.
2. Создать `.env`:
```bash
cp .env.example .env
```
3. Заполнить минимум:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_OWNER_CHAT_ID`
- хотя бы один ключ LLM: `GEMINI_API_KEY` или другой провайдер
4. Поднять контейнер:
```bash
docker compose up -d --build
```
5. Проверить:
```bash
docker compose logs -f vito
```
6. Проверить комплект переноса:
```bash
bash scripts/verify_repro_bundle.sh
```

## Локальный запуск без Docker
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
cp .env.example .env
bash scripts/verify_repro_bundle.sh
python3 -u main.py
```

## Перенос памяти
- если нужен чистый новый экземпляр: не переносить `memory/`
- если нужен тот же накопленный экземпляр:
  - перенести `memory/vito_local.db`
  - перенести `memory/chroma_db/`

## Перенос browser-сессий
Если нужны уже подтвержденные логины, перенести соответствующие `storage_state` файлы из `runtime/`:
- `gumroad_storage_state.json`
- `etsy_storage_state.json`
- `kdp_storage_state.json`
- `twitter_storage_state.json`
- `reddit_storage_state.json`
- `pinterest_storage_state.json`
- `printful_storage_state.json`

## Что не переносить
- `logs/`
- временные отчеты и артефакты из `reports/`, если они не нужны как evidence
- локальные dump/скриншоты, не относящиеся к рабочим runbooks

## Минимальная проверка после старта
1. Проверить, что бот отвечает в Telegram.
2. Проверить `/health`.
3. Проверить dashboard/API.
4. Проверить один безопасный сценарий:
   - запрос в TG
   - response
   - owner task state
   - memory write
5. Только потом проверять browser/platform flows.

## Режимы переноса
- `Stateless test`: код + `.env`, без `memory/` и `runtime/`
- `Warm migration`: код + `.env` + `memory/`
- `Full continuity`: код + `.env` + `memory/` + нужные `runtime/*storage_state.json`
