# Platform Test Matrix (2026-03-04)

## Почему раньше выглядело как «только Gumroad»
- Боевой live publish реально запускался в этом пакете именно для Gumroad (потому что по нему есть готовый browser pipeline).
- По остальным платформам были dry-run/live-probe прогоны, но без отдельной сводки это выглядело неочевидно.

## Что прогнано сейчас
- `reports/VITO_ALL_PLATFORMS_PROBE_2026-03-04_1016UTC.json`
- `reports/VITO_PLATFORM_AUTH_LIVE_PROBE_2026-03-04_1014UTC.json`
- `reports/VITO_PLATFORM_E2E_DRYRUN_2026-03-04_1014UTC.json`
- `reports/VITO_SOCIAL_SDK_DRYRUN_2026-03-04_1014UTC.json`
- `reports/VITO_SOCIAL_LIVE_PROBE_2026-03-04_1014UTC.json`

## Результат по всем платформам (кратко)
- Gumroad: `auth_ok=true`, dry-run publish `prepared`, отдельный live browser test выполнен (draft creation failed: `draft_not_created`).
- Etsy: auth fail (403 API key/secret mismatch or inactive), dry-run `prepared`.
- Printful: `auth_ok=true`, dry-run `prepared`.
- Ko-fi: `auth_ok=true`, dry-run `prepared`.
- Twitter/X: auth fail (401), dry-run `prepared`, delete-probe `not_authenticated`.
- Reddit: auth fail (по текущей конфигурации), dry-run `prepared`.
- YouTube: auth fail (нет рабочего OAuth runtime), dry-run `prepared`.
- Amazon KDP: `auth_ok=false`, publish status `no_browser` (в platform adapter нет живого browser agent в этом рантайме).
- Threads/TikTok: auth fail, dry-run `prepared`.
- WordPress: not configured / dry-run `prepared`.
- Medium: not configured.
- Substack/Creative Fabrica: `no_browser`.
- Instagram/LinkedIn/Pinterest/Shopify: instantiation error (адаптеры не реализуют обязательные методы base interface полностью).

## Главные блокеры до «live publish/delete везде»
1. Не у всех платформ adapter-класс полноценно реализован (часть абстрактных методов отсутствует).
2. Для части сервисов ключи/токены невалидны или не активированы (Etsy/Twitter/YouTube/Reddit).
3. Для browser-only сценариев нужен единый runtime browser agent (сейчас не везде подключён).
4. Нет унифицированного `delete` контракта для всех платформ (сейчас точечно, напр. `delete_tweet`).

## Что исправлять следующим пакетом
1. Дореализовать интерфейс adapter-ов: `health_check/get_analytics` для Instagram/LinkedIn/Pinterest/Shopify.
2. Ввести общий контракт `delete_listing/delete_post` для всех платформ где это возможно.
3. Поднять единый browser runtime слой и перепривязать KDP/Substack/CreativeFabrica browser flows.
4. После этого прогнать live smoke publish+delete по каждой платформе и сохранить evidence.
