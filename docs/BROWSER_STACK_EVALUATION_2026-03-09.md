# Browser Stack Evaluation — 2026-03-09

Статус: `APPROVED_WITH_CONSTRAINTS`

## Базовый вывод

На текущем этапе VITO должен оставаться на `Playwright Chromium` как основном browser runtime.

Причина:
- текущий код уже глубоко завязан на Playwright contexts/storage_state;
- platform adapters и auth helpers используют один и тот же контракт;
- главная проблема сейчас не в том, что "Playwright слабый", а в отсутствии единого runtime policy слоя.

## Что нужно считать обязательным

1. `Screenshot-first` для хрупких flow:
- Etsy
- Gumroad
- Ko-fi
- Printful
- Pinterest
- Reddit
- Amazon KDP

2. Единый `auth interrupt` контракт:
- OTP / 2FA
- interactive auth
- profile completion gates

3. Session isolation:
- отдельный storage_state по сервису;
- отдельные runtime profiles по сервису;
- никакого неявного reuse чужой browser session.

## Про patchright

`patchright` можно рассматривать только как controlled evaluation path, не как немедленную замену.

Причины:
- он может помочь с anti-bot detection на части площадок;
- но добавляет новый operational surface;
- без controlled A/B verification он может просто усложнить debugging.

## Решение

1. `Playwright` остается production-default.
2. `patchright` допускается только как экспериментальный backend после:
- capability map;
- reproducible auth/session path;
- regression tests;
- controlled side-by-side probes.

## Условия допуска patchright

Patchright можно включать только если одновременно выполняются:
- есть отдельный adapter/backend toggle;
- есть isolated browser profile;
- есть equal scenario replay on same platform;
- есть объективное улучшение success rate без роста regressions.

## Что считать завершением Phase E по browser stack

- browser runtime policy внедрен;
- auth interrupts унифицированы;
- screenshot-first режим реально меняет runtime behavior;
- profile completion runbooks живут в коде;
- стек Playwright закреплен как default;
- patchright оставлен как controlled future path, а не ad-hoc switch.
