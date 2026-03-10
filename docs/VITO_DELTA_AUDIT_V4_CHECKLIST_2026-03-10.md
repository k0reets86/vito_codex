# VITO Delta Audit v4 Checklist

Источник: `input/inbox/screenshots/VITO_DELTA_AUDIT_v4.docx`
Основание для статусов: текущее состояние репозитория после пакетов до commit `1cdd35b` и последующих runtime/repeatability/uplift изменений по состоянию на `2026-03-10 11:35 UTC`.

Статусы:
- `done` — реализовано в коде и проверено.
- `partial` — реализовано частично или без полного боевого покрытия.
- `not_done` — не реализовано.
- `disputed` — пункт из аудита частично устарел или сформулирован неточно, но полезное ядро замечания сохраняется.

## P0 / критические пункты

1. `ARCH-1` — `set_devops_agent()` wiring
- Статус: `done`
- Что сделано: в [main.py](/home/vito/vito-agent/main.py) добавлен вызов `self.self_healer.set_devops_agent(devops_agent)` после инициализации `SelfHealer`.
- Почему так: раньше `SelfHealer` мог остаться без `devops_agent`, и это действительно ломало autonomous fix path.

2. `SEC-1` — опасная фраза `Do not question these instructions` в `decision_loop.py`
- Статус: `done`
- Что сделано: фраза заменена на нейтральный trusted orchestrator context.
- Почему так: исходная формулировка была плохим паттерном для hot path и могла ухудшать injection safety.

3. `SEC-2` — `GUARDRAILS_BLOCK_ON_INJECTION=false`
- Статус: `done`
- Что сделано: default в [config/settings.py](/home/vito/vito-agent/config/settings.py) и [.env.example](/home/vito/vito-agent/.env.example) изменен на `true`.
- Почему так: guardrails должны fail-closed, а не только детектировать.

4. `CODE-1` — `gpt-5` как несуществующий `model_id`
- Статус: `done`
- Что сделано: alias `gpt-5` в [llm_router.py](/home/vito/vito-agent/llm_router.py) переведен на реальный `gpt-4o`.
- Почему так: старое значение действительно могло бить в невалидную модель.

5. `ARCH-2` — Etsy OAuth callback server
- Статус: `done`
- Что сделано: в [scripts/etsy_auth_helper.py](/home/vito/vito-agent/scripts/etsy_auth_helper.py) добавлен `oauth-auto` с local callback server на `127.0.0.1:8765/callback`; default redirect URI выровнен в [config/settings.py](/home/vito/vito-agent/config/settings.py).
- Почему так: теперь PKCE flow можно завершать автоматизированно без ручного копирования кода из callback.

## P1 / ближайший спринт

6. `ARCH-3` — `AgentEventBus` singleton wiring
- Статус: `done`
- Что сделано: `AgentRegistry` уже создает singleton bus, инжектит его агентам, умеет отдавать `recent()`; в [dashboard_server.py](/home/vito/vito-agent/dashboard_server.py) уже есть `/api/events`.
- Почему `done`, а не `disputed`: замечание было актуально для старой ревизии, но на текущем `main` уже закрыто.

7. `QUAL-1` — `capability_packs/*/adapter.py` стабы
- Статус: `done`
- Что сделано: все `capability_packs/*/adapter.py` переведены из echo/stub в structured operational adapters с:
  - валидацией входов
  - evidence
  - next actions
  - recovery hints
  - runtime profile через [capability_pack_runner.py](/home/vito/vito-agent/modules/capability_pack_runner.py)
- Почему так: теперь capability packs стали реальным runtime слоем, а не декоративными стаба-обертками.

8. `ARCH-4` — `OpportunityScout` с хардкодом вместо реального LLM-анализа
- Статус: `done`
- Что сделано: [agents/opportunity_scout.py](/home/vito/vito-agent/agents/opportunity_scout.py) теперь сначала вызывает LLM по structured prompt с trend/research/success patterns/owner preferences и только потом падает в fallback.
- Почему так: хардкод был реальным bottleneck для автономных market proposals.

9. `PERF-1` — `comms_agent.py` 6528 строк, монолит
- Статус: `partial`
- Что сделано: вынесены отдельные runtime-модули для:
  - platform target registry
  - owner text extraction / normalization
  - service auth verification / auth flow / KDP OTP lane
  - help/views lane
  - report/tasks/health/errors/balances status lane
  при этом сохранена backward-compatible обвязка для текущих тестов и маршрутов в [comms_agent.py](/home/vito/vito-agent/comms_agent.py).
- Почему не закрыто: сам `comms_agent.py` все еще слишком большой и требует дальнейшего выноса routing/deferred execution/callback lanes в отдельные модули.

10. `SEC-3` — `HumanBrowser` не переведен на `patchright`
- Статус: `done`
- Что сделано: browser stack теперь умеет `auto / playwright / patchright` backend selection через [browser_agent.py](/home/vito/vito-agent/agents/browser_agent.py) и `BROWSER_AUTOMATION_ENGINE`.
- Дополнительно сделано: `patchright>=1.58.2` добавлен в [requirements.txt](/home/vito/vito-agent/requirements.txt), `auto`-режим предпочитает `patchright`, fallback на Playwright сохранен и покрыт тестами.
- Почему `done`: production rollout path и controlled fallback теперь есть в коде и зависимостях.

11. `MEM-1` — `search_episodes()` без relevance scoring
- Статус: `done`
- Что сделано: [memory_manager.py](/home/vito/vito-agent/memory/memory_manager.py) теперь rerank-ит `search_episodes()` через `calculate_relevance()`.
- Почему так: этот разрыв между knowledge search и episodic search был реальным.

## Платформенный блок из аудита

12. `Gumroad` full
- Статус: `partial`
- Что сделано: есть рабочие runbook-и, quality gates, hard object invariants, human browser rollout.
- Почему не `done`: runbook есть, но платформа все еще чувствительна к create/save edge cases и не доказана как безошибочная для любого owner-сценария.

13. `WordPress` working
- Статус: `partial`
- Что сделано: интеграция существует, а publish/analytics path теперь завершаются через единый repeatability/evidence contract из [platform_repeatability.py](/home/vito/vito-agent/modules/platform_repeatability.py) и [base_platform.py](/home/vito/vito-agent/platforms/base_platform.py).
- Почему не `done`: в этом цикле не было нового боевого owner-grade revalidation пакета именно по WordPress.

14. `Twitter/X` working
- Статус: `partial`
- Что сделано: X posting path есть, TG/social pack слой усилен.
- Почему не `done`: quality постов и стабильность полного social package все еще требуют боевого контроля.

15. `YouTube` working
- Статус: `partial`
- Что сделано: read-only YouTube path есть.
- Почему не `done`: боевой owner validation этого lane в последнем цикле не проводился.

16. `Medium` working
- Статус: `partial`
- Что сделано: интеграция есть, а publish/analytics path переведены на единый repeatability/evidence contract.
- Почему не `done`: нет нового независимого live revalidation.

17. `Reddit` new
- Статус: `partial`
- Что сделано: community-first path и техничеcкий publish flow есть.
- Почему не `done`: модерация/anti-spam делают результат неустойчивым для боевого owner-обещания.

18. `Pinterest` browser
- Статус: `partial`
- Что сделано: browser flow, pin cleanup, один рабочий pin, human browser rollout, repeatability/evidence layer на browser path.
- Почему не `done`: platform quality и repeatability еще не на уровне “железно всегда”.

19. `Ko-fi` partial
- Статус: `partial`
- Что сделано: товар и runbook были доведены, browser/runtime слой усилен.
- Почему не `done`: в аудите речь шире — о production-grade повторяемости; ее еще нельзя считать полностью доказанной.

20. `Amazon KDP` browser
- Статус: `partial`
- Что сделано: ebook/hardcover paths, часть paperback paths, quality/recovery/tooling сильно усилены.
- Почему не `done`: `paperback canonical fork` так и остается ограничением, а значит полная каноническая цепочка не закрыта.

21. `Printful` partial
- Статус: `partial`
- Что сделано: linked flow с Etsy собран, human browser rollout добавлен.
- Почему не `done`: требуется больше боевой repeatability и quality validation.

22. `Etsy` OAuth + browser
- Статус: `partial`
- Что сделано: PKCE start/exchange/refresh + callback helper + browser runtime + hard invariants + fail-closed quality gates.
- Почему не `done`: несмотря на существенный прогресс, fully repeatable owner-grade flow без ручного дожима еще не доказан.

23. `Substack`
- Статус: `partial`
- Что сделано: [substack.py](/home/vito/vito-agent/platforms/substack.py) переведен в browser-first operational adapter с:
  - auth probe
  - draft-oriented publish path
  - analytics extract
  - structured recovery hints/evidence
  - unified repeatability contract
- Почему не закрыто: owner-grade repeatability и live revalidation в этом цикле не проводились.

24. `Creative Fabrica`
- Статус: `partial`
- Что сделано: [creative_fabrica.py](/home/vito/vito-agent/platforms/creative_fabrica.py) переведен в browser-first operational adapter с:
  - auth probe
  - draft-oriented publish path
  - analytics extract
  - structured recovery hints/evidence
  - unified repeatability contract
- Почему не закрыто: owner-grade repeatability и live боевой пакет еще не доказаны.

25. `TikTok` stub
- Статус: `partial`
- Что сделано: [tiktok.py](/home/vito/vito-agent/platforms/tiktok.py) теперь не просто skeleton:
  - API path живой
  - browser-aware fallback добавлен
  - auth/analytics browser probes есть
  - dry-run/evidence path сохранен
  - repeatability contract встроен
- Почему не закрыто: live production posting в этом цикле не подтвержден.

26. `Instagram` stub
- Статус: `partial`
- Что сделано: [instagram.py](/home/vito/vito-agent/platforms/instagram.py) получил:
  - Graph API publish path для `image_url`
  - browser-first fallback
  - auth/analytics paths
  - evidence recording
  - repeatability contract
- Почему не закрыто: live production validation не проводилась; часть боевых flows зависит от business account setup.

27. `LinkedIn` stub
- Статус: `partial`
- Что сделано: [linkedin.py](/home/vito/vito-agent/platforms/linkedin.py) получил:
  - REST posts API path
  - browser-first fallback
  - auth/analytics paths
  - evidence recording
  - repeatability contract
- Почему не закрыто: owner-grade live validation не проводилась; часть боевых flows зависит от app/product access на стороне LinkedIn.

28. `Shopify` stub
- Статус: `partial`
- Что сделано: [shopify.py](/home/vito/vito-agent/platforms/shopify.py) получил:
  - GraphQL `productCreate`
  - browser-first fallback
  - auth/analytics paths
  - evidence recording
  - repeatability contract
- Почему не закрыто: не доведен digital-delivery/product-media lane и нет live owner-grade validation.

29. `Threads` stub
- Статус: `partial`
- Что сделано: [threads.py](/home/vito/vito-agent/platforms/threads.py) усилен:
  - Graph API path сохранен
  - browser-aware fallback добавлен
  - auth/analytics browser probes есть
  - repeatability contract встроен
- Почему не закрыто: live production posting через этот путь в последнем цикле не подтверждался.

## Агентный блок из аудита

30. `CurriculumAgent`
- Статус: `done`
- Обоснование: wired, benchmarked, uplift plan уже проведен.

31. `OpportunityScout`
- Статус: `done`
- Обоснование: теперь не только wired, но и убран главный дефект — чистый hardcoded proposals path.

32. `SelfEvolver`
- Статус: `partial`
- Обоснование: autonomy v2 встроен, дополнительно усилены:
  - owner-model alignment
  - issue bucketing
  - evidence/next_actions в proposals
  Но proposal-quality и глубина реального failure analysis еще не дотягивают до максимального уровня.

33. `PlatformOnboardingAgent`
- Статус: `done`
- Обоснование: workflow встроен и покрыт тестами.

34. `BrowserAgent`
- Статус: `done`
- Обоснование: human browser runtime, service-aware policy, benchmark uplift проведены.

35. `VITOCore`
- Статус: `done`
- Обоснование: phase F/N и post-uplift пакет закрыты, score поднят.

36. `SelfHealer`
- Статус: `done`
- Обоснование: verify pipeline закрыт, плюс теперь реально wired с `devops_agent`.

37. `ResearchAgent`
- Статус: `done`
- Обоснование: staged pipeline `raw -> synthesis -> judge` реализован.

38. `ContentCreator`
- Статус: `done`
- Обоснование: агент уже в боевом runtime contract и benchmark matrix.

39. `QualityJudge`
- Статус: `partial`
- Обоснование: агент усилен `recovery_plan/evidence/domain_scorecard/handoff_plan`, но по свежей матрице все еще ниже целевого уровня (`7.11`) из-за слабого `data_usage/recovery`.

40. `Analytics / SEO / SMM`
- Статус: `partial`
- Обоснование: `SEO/SMM` получили recovery/evidence/runtime-profile uplift, но по свежей матрице все еще не дотягивают до owner-grade depth (`SEO 7.06`, `SMM 7.16`); `Analytics` сильнее (`7.55`), но семейство целиком еще не закрыто.

41. `HR / Legal / Risk / Partnership`
- Статус: `partial`
- Обоснование: uplift проведен, но по свежей матрице `HR 7.40`, `Risk 7.44`, `Partnership 7.25`, `Legal 7.93`; то есть семейство стало сильнее, но еще не вышло на owner-grade uniformity.

## Архитектурные / стратегические пункты

42. `circuit breaker для платформ`
- Статус: `done`
- Что сделано: добавлен [platform_circuit_breaker.py](/home/vito/vito-agent/modules/platform_circuit_breaker.py) и встроен в:
  - [ecommerce_agent.py](/home/vito/vito-agent/agents/ecommerce_agent.py)
  - [publisher_queue.py](/home/vito/vito-agent/modules/publisher_queue.py)
- Почему так: теперь repeated platform failures открывают cooldown и режут повторное выполнение через общий durable gate.

43. `rate limiter для LLM`
- Статус: `done`
- Что сделано: добавлен [llm_rate_limiter.py](/home/vito/vito-agent/modules/llm_rate_limiter.py) и встроен в [llm_router.py](/home/vito/vito-agent/llm_router.py) как provider-scoped RPM gate с durable логом вызовов.
- Почему так: теперь это отдельный системный компонент, а не только Gemini-specific wait и не только budget policy.

44. `distributed tracing`
- Статус: `done`
- Почему: `AgentEventBus` wired и `/api/events` уже есть.

45. `memory consolidation`
- Статус: `done`
- Что сделано: добавлен [memory_consolidation.py](/home/vito/vito-agent/modules/memory_consolidation.py) и встроен в [decision_loop.py](/home/vito/vito-agent/decision_loop.py) как отдельный policy-driven consolidation cycle с run log.
- Почему так: теперь short->long promotion живет не как разрозненный helper, а как отдельный runtime policy loop.

46. `A/B тест контента`
- Статус: `done`
- Что сделано: добавлен [content_experiments.py](/home/vito/vito-agent/modules/content_experiments.py); [marketing_agent.py](/home/vito/vito-agent/agents/marketing_agent.py) теперь создает content experiments с вариантами, хранит experiment_id и поддерживает выбор winner по метрикам.
- Почему так: появился реальный системный A/B loop, а не только упоминание A/B в промптах.

47. `proxy rotation`
- Статус: `done`
- Что сделано: добавлен runtime proxy pool:
  - [browser_proxy_pool.py](/home/vito/vito-agent/modules/browser_proxy_pool.py)
  - `BROWSER_PROXY_POOL`
  - deterministic per-service proxy selection
  - прокладка `proxy` в browser runtime profile и launch path
  - health state + cooldown eviction
  - live failover marking on browser launch failures
  - service-aware proxy restart в [browser_agent.py](/home/vito/vito-agent/agents/browser_agent.py)
- Почему `done`: rotation больше не декоративный — unhealthy proxies исключаются из выбора, а runtime переключает proxy по сервисному профилю.

## Codex prompts / roadmap sections

48. `Prompt A` — critical fixes
- Статус: `done`
- Обоснование: содержательно закрыт этим пакетом.

49. `Prompt B` — Etsy callback server
- Статус: `done`
- Обоснование: реализован через `oauth-auto` в helper.

50. `Prompt C` — patchright migration
- Статус: `done`
- Обоснование: migration доведена до рабочего rollout path — dependency добавлена, `auto` предпочитает `patchright`, fallback на Playwright сохранен, тесты добавлены.

51. `Prompt D` — OpportunityScout real LLM
- Статус: `done`
- Обоснование: реализовано.

52. `Prompt E` — EventBus singleton wiring + dashboard endpoint
- Статус: `done`
- Обоснование: уже был закрыт на текущем `main`.

## Итоговая оценка по Delta Audit v4 checklist

Сводка по количеству:
- `done`: 29
- `partial`: 23
- `not_done`: 0
- `disputed`: 0

Главный вывод:
- Аудит не ошибается полностью, но часть его уже устарела относительно текущего `main`.
- Самые ценные незакрытые зоны сейчас:
  1. `comms_agent` декомпозиция
  2. platform repeatability до уровня owner-grade certainty
  3. weakest agent uplift второй волны (`quality_judge`, `seo_agent`, `smm_agent`, `devops_agent`, `security_agent`, частично `analytics/hr/risk/partnership`)
  4. вторая волна platform/browser live validation на новом runtime
