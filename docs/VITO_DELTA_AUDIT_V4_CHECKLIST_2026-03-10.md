# VITO Delta Audit v4 Checklist

Источник: `input/inbox/screenshots/VITO_DELTA_AUDIT_v4.docx`
Основание для статусов: текущее состояние репозитория на commit `1cdd35b`.

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
- Статус: `not_done`
- Что сделано: прямой декомпозиции файла пока нет.
- Почему не закрыто: это архитектурный долг, а не ложное замечание. Да, часть логики была вынесена в compiler/router/runtime, но сам монолит еще жив.

10. `SEC-3` — `HumanBrowser` не переведен на `patchright`
- Статус: `not_done`
- Что сделано: безопасный browser runtime слой добавлен, но миграции на `patchright` нет.
- Почему не закрыто: browser resilience улучшен, но именно этот пункт из аудита остается открытым.

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
- Что сделано: интеграция существует.
- Почему не `done`: в этом цикле не было нового боевого revalidation пакета именно по WordPress.

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
- Что сделано: интеграция есть.
- Почему не `done`: нет нового независимого live revalidation.

17. `Reddit` new
- Статус: `partial`
- Что сделано: community-first path и техничеcкий publish flow есть.
- Почему не `done`: модерация/anti-spam делают результат неустойчивым для боевого owner-обещания.

18. `Pinterest` browser
- Статус: `partial`
- Что сделано: browser flow, pin cleanup, один рабочий pin, human browser rollout.
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
- Статус: `not_done`
- Что сделано: интеграция есть как browser-only.
- Почему не закрыто: по аудиту нужен production-grade path, его в этом цикле не доводили.

24. `Creative Fabrica`
- Статус: `not_done`
- Что сделано: базовый browser-only слой есть.
- Почему не закрыто: хрупкость runbook-а не убрана и live боевого пакета не было.

25. `TikTok` stub
- Статус: `not_done`
- Что сделано: по сути ничего достаточного для снятия замечания.

26. `Instagram` stub
- Статус: `not_done`
- Что сделано: production implementation не делалась.

27. `LinkedIn` stub
- Статус: `not_done`
- Что сделано: production implementation не делалась.

28. `Shopify` stub
- Статус: `not_done`
- Что сделано: production implementation не делалась.

29. `Threads` stub
- Статус: `not_done`
- Что сделано: production implementation не делалась.

## Агентный блок из аудита

30. `CurriculumAgent`
- Статус: `done`
- Обоснование: wired, benchmarked, uplift plan уже проведен.

31. `OpportunityScout`
- Статус: `done`
- Обоснование: теперь не только wired, но и убран главный дефект — чистый hardcoded proposals path.

32. `SelfEvolver`
- Статус: `partial`
- Обоснование: autonomy v2 встроен, но в аудите справедливо отмечено, что proposal-quality и глубина реального failure analysis еще не максимальны.

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
- Обоснование: агент сильно усилен, но все еще остается одним из слабейших по benchmark matrix и требует post-uplift следующей волны.

40. `Analytics / SEO / SMM`
- Статус: `partial`
- Обоснование: они уже не thin wrappers в старом смысле, но глубокая operational depth еще не дотянута до целевого уровня.

41. `HR / Legal / Risk / Partnership`
- Статус: `partial`
- Обоснование: существенный uplift уже был, но замечание про недостаточную боевую глубину еще частично справедливо.

## Архитектурные / стратегические пункты

42. `circuit breaker для платформ`
- Статус: `done`
- Что сделано: добавлен [platform_circuit_breaker.py](/home/vito/vito-agent/modules/platform_circuit_breaker.py) и встроен в:
  - [ecommerce_agent.py](/home/vito/vito-agent/agents/ecommerce_agent.py)
  - [publisher_queue.py](/home/vito/vito-agent/modules/publisher_queue.py)
- Почему так: теперь repeated platform failures открывают cooldown и режут повторное выполнение через общий durable gate.

43. `rate limiter для LLM`
- Статус: `partial`
- Почему: есть budget/controller/policy слои, но прямой rate-limiter как отдельный системный компонент не доведен до уровня замечания.

44. `distributed tracing`
- Статус: `done`
- Почему: `AgentEventBus` wired и `/api/events` уже есть.

45. `memory consolidation`
- Статус: `partial`
- Почему: memory pipeline сильно усилен, но именно как отдельный ночной consolidation job с полным policy loop тема еще не исчерпана.

46. `A/B тест контента`
- Статус: `not_done`
- Почему: системного A/B loop нет.

47. `proxy rotation`
- Статус: `not_done`
- Почему: не реализовывалось.

## Codex prompts / roadmap sections

48. `Prompt A` — critical fixes
- Статус: `done`
- Обоснование: содержательно закрыт этим пакетом.

49. `Prompt B` — Etsy callback server
- Статус: `done`
- Обоснование: реализован через `oauth-auto` в helper.

50. `Prompt C` — patchright migration
- Статус: `not_done`
- Обоснование: не реализовывалось.

51. `Prompt D` — OpportunityScout real LLM
- Статус: `done`
- Обоснование: реализовано.

52. `Prompt E` — EventBus singleton wiring + dashboard endpoint
- Статус: `done`
- Обоснование: уже был закрыт на текущем `main`.

## Итоговая оценка по Delta Audit v4 checklist

Сводка по количеству:
- `done`: 22
- `partial`: 17
- `not_done`: 13
- `disputed`: 0

Главный вывод:
- Аудит не ошибается полностью, но часть его уже устарела относительно текущего `main`.
- Самые ценные незакрытые зоны сейчас:
  1. `comms_agent` декомпозиция
  2. `capability_packs` из stub в real runtime
  3. `patchright migration`
  4. platform repeatability до уровня owner-grade certainty
  5. weakest agent uplift второй волны (`quality_judge`, `seo_agent`, `smm_agent`, `devops_agent`, `security_agent`)
