# LLM Mode Switch (Free vs Prod)

Быстрое переключение режима делается командой в Telegram:

- `/llm_mode free` — тестовый профиль (все задачи через `gemini-2.5-flash`)
- `/llm_mode prod` — боевой профиль (роутер по типам задач: Sonnet/o3/Opus/Perplexity и т.д.)
- `/llm_mode status` — показать текущее состояние

Ключи в `.env`:

- `LLM_ROUTER_MODE=free|prod` — человекочитаемый режим
- `LLM_FORCE_GEMINI_FREE=true|false` — принудительно гнать все задачи в Gemini
- `LLM_FORCE_GEMINI_MODEL=gemini-2.5-flash` — модель Gemini для free-режима
- `LLM_ENABLED_MODELS` / `LLM_DISABLED_MODELS` — allow/deny списки моделей

Gemini free-стек (включается профилем `free`):

- `GEMINI_ENABLE_GROUNDING_SEARCH=true`
- `GEMINI_ENABLE_URL_CONTEXT=true`
- `GEMINI_EMBEDDINGS_ENABLED=true`
- `GEMINI_EMBED_MODEL=gemini-embedding-001`
- `GEMINI_ENABLE_IMAGEN=true`
- `GEMINI_LIVE_API_ENABLED=true`
- `IMAGE_ROUTER_PREFER_GEMINI=true`

Лимиты:

- `GEMINI_FREE_MAX_RPM=15`
- `GEMINI_FREE_TEXT_RPD=1000`
- `GEMINI_FREE_SEARCH_RPD=1500`

Примечание: после переключения режим применяется сразу, но для чистого состояния цикла рекомендуется перезапуск процесса VITO.
