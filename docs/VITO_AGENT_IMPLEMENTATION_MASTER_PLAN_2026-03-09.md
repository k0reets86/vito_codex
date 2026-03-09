# VITO Agent Implementation Master Plan — 2026-03-09

Статус: `MANDATORY`

Источник:
- `input/inbox/screenshots/VITO_AGENTS_DEEP_2026.docx`
- `input/inbox/screenshots/VITO_INTERACTION_MAP_2026.docx`
- `input/inbox/screenshots/VITO_IMPL_GUIDE_2026.docx`
- `docs/VITO_UPGRADE_MASTER_PLAN_2026-03-09.md`

## 0. Цель

Довести агентный слой VITO до состояния, где:
- каждый агент является реальной автономной боевой единицей со своим operational lane;
- межагентные связи работают как исполняемая система, а не как статическая схема;
- у каждого агента есть owned outcomes, runtime contracts, доказуемые benchmarks и реальные data/tool paths;
- VITOCore, final verifier и QualityJudge собирают результаты агентов и не дают системе считать thin-wrapper поведение зрелым;
- VITO может через агентов стабильно выполнять сквозные workflow, а не только отдельные шаги.

Обязательное уточнение:
- план покрывает **все 23 агента без исключений**;
- план покрывает **все обязательные связи из карты взаимодействий**, а не только самые важные;
- план покрывает **все обязательные workflow**, а не только `W01-W04`;
- `done` невозможен, если хотя бы один агент, обязательная связь или обязательный workflow остались “на потом”.

## 1. Неподвижные правила

### 1.1 Никаких thin-wrapper агентов
Агент не считается зрелым, если он:
- только пишет LLM-ответ;
- не имеет своих runtime inputs/data sources;
- не может дать evidence;
- не умеет делегировать и принимать результаты через registry.

### 1.2 Все связи только через registry/contract layer
Межагентные вызовы идут только через:
- `registry.dispatch(...)`
- `BaseAgent.ask(...)`
- `BaseAgent.delegate(...)`
- event/runtime contracts

Прямые импорты другого агента как рабочего integration path запрещены.

### 1.3 Каждый агент обязан иметь боевой benchmark
Без фиксированного benchmark task агент не может считаться `done`.

### 1.4 Каждая связь обязана менять runtime
Если связь описана только в markdown, но не влияет на исполняемый маршрут, она считается нереализованной.

### 1.5 Никакой частичной сдачи агентного плана
Нельзя:
- закрыть только часть агентов;
- закрыть только слабых агентов;
- закрыть только часть связей;
- закрыть только часть workflow.

Агентный план считается завершенным только при полном покрытии всех 23 агентов, всех обязательных связей и всех обязательных workflow.

## 2. Жесткая оценка из анализа агентов

### 2.1 Боевые агенты
- `TrendScout`
- `DevOpsAgent`
- `ResearchAgent`
- `SecurityAgent`

### 2.2 Рабочие, но недожатые
- `VITOCore`
- `ECommerceAgent`
- `ContentCreator`
- `QualityJudge`
- `HRAgent`
- `DocumentAgent`
- `BrowserAgent`
- `PublisherAgent`
- `AnalyticsAgent`
- `SMMAgent`
- `AccountManager`
- `SelfHealer`

### 2.3 Thin-wrapper / слабые агенты
- `MarketingAgent`
- `EconomicsAgent`
- `SEOAgent`
- `EmailAgent`
- `TranslationAgent`
- `LegalAgent`
- `RiskAgent`
- `PartnershipAgent`

Это не просто оценка, а приоритет на реализацию.

## 3. Что обязательно реализовать из карты взаимодействий

### 3.1 Interaction substrate
Нужно вшить в код:
- `BaseAgent.ask(...)`
- `BaseAgent.delegate(...)`
- `registry.set_registry(...)` для всех агентов
- `NEEDS` / `CAPABILITIES` декларации
- `collaboration_contract`
- runtime event contracts
- `QualityGate` для publish/listing/content-required действий
- `EventBus.emit(...)` или эквивалентный signal layer для async handoff

### 3.2 202 связи не делать вслепую
Реализовать не “все сразу”, а слоями:
1. `trigger`
2. `data`
3. `request`
4. `feedback`
5. `block`

Каждая связь должна быть отнесена к одному из пяти типов и пройти runtime test.

Но итоговая цель не выборочное покрытие, а полное: все обязательные связи из карты должны иметь либо runtime implementation, либо явный documented block reason.

### 3.3 Сквозные workflow как основной критерий
Главный критерий — не количество связей, а выполнение 8 сквозных workflow:
- `W01` Создание и продажа цифрового продукта
- `W02` Публикация контента
- `W03` Мониторинг и самовосстановление
- `W04` Управление аккаунтами и 2FA
- `W05` Социальный запуск
- `W06` Аналитика и реакция на данные
- `W07` Compliance / legal / risk gating
- `W08` Skill growth / self-upgrade

Все восемь workflow обязательны. Частичная реализация `W01-W04` не считается завершением агентного плана.

## 4. Фазы реализации

## Phase I — Agent Interaction Substrate
Цель: сделать связи между агентами исполняемыми.

Сделать:
1. Вшить `BaseAgent.ask(...)` и `BaseAgent.delegate(...)` как обязательный стандарт.
2. Гарантированно привязать `registry` ко всем агентам на старте.
3. Ввести `NEEDS` / `CAPABILITIES` декларации для всех агентов.
4. Добавить runtime validation: агент не может объявить capability без benchmark и evidence contract.
5. Добавить event bus / signal layer для async handoff, не ломая существующий код.
6. Добавить `QualityGate` decorator/обертку для действий:
   - `publish`
   - `listing_create`
   - `listing_update`
   - `product_create`
   - `content_publish`
7. Зафиксировать backward-compatible rollout:
   - если новый handoff не нашел агента через registry, он возвращает `None` и не ломает старый workflow;
   - если capability найден, новый путь обязан писать runtime trace.

Критерий завершения:
- любой агент может запросить другой агент через единый путь;
- связи работают без прямых импортов;
- runtime traces показывают реальный handoff.

## Phase J — Core Workflow Wiring
Цель: собрать основные сквозные workflow из карты взаимодействий.

Сделать:
1. `W01` digital product sales loop:
   - Core -> TrendScout -> Research -> Economics -> Legal -> Content -> Judge -> SEO -> Translation -> ECommerce -> Browser -> Publish -> Analytics
2. `W02` content publication loop
3. `W03` monitoring/self-heal loop
4. `W04` account/auth loop
5. `W05` social launch loop
6. `W06` analytics-response loop
7. `W07` compliance/risk gating loop
8. `W08` skill growth/self-upgrade loop

Критерий завершения:
- workflow виден как chain из runtime events;
- handoff не декоративный, а влияет на следующий шаг.

## Phase K — Thin-Wrapper Agent Uplift
Цель: превратить всех слабых агентов в реальные operational units, не оставив ни одного wrapper-only агента.

Приоритет P0:
1. `SEOAgent`
   - pytrends / keyword data
   - rankings/recommendations
   - SEO briefs вместо общих LLM-советов
2. `MarketingAgent`
   - TrendScout/Analytics inputs
   - launch strategy templates
   - platform-specific promotion plans
3. `EconomicsAgent`
   - competitor price data
   - price recommendation logic
   - dynamic repricing triggers
4. `LegalAgent`
   - cached platform TOS
   - policy diff monitor
   - publish blockers
5. `RiskAgent`
   - reputation / spam / moderation signals
   - launch/publish risk scoring

Приоритет P1:
6. `EmailAgent`
   - real SMTP path
   - subscriber storage
   - delivery evidence
7. `TranslationAgent`
   - real provider path
   - cache
   - consistency checks
8. `PartnershipAgent`
   - affiliate/opportunity search
   - outreach artifacts

Критерий завершения:
- каждый из этих агентов больше не thin-wrapper;
- у каждого есть 1+ реальные data/tool integrations и benchmarks.

## Phase L — Tier-2 Agent Hardening
Цель: добить всех рабочих, но нестабильных агентов и довести покрытие до всех 23 агентов.

Приоритет:
1. `BrowserAgent`
2. `ECommerceAgent`
3. `AccountManager`
4. `VITOCore`
5. `ContentCreator`
6. `SMMAgent`
7. `AnalyticsAgent`
8. `PublisherAgent`
9. `DocumentAgent`
10. `QualityJudge`
11. `HRAgent`
12. `SelfHealer`

Для каждого:
- owned outcomes
- evidence schema
- failure modes
- collaboration contracts
- benchmark tasks
- fail-closed verifier integration

Критерий завершения:
- у каждого агента есть runtime proof-of-work и стабильный operational lane.

## Phase M — Agent Benchmark Matrix
Цель: сделать по каждому агенту обязательный боевой тест.

Сделать:
1. один benchmark task минимум на агента;
2. один cross-agent benchmark на группу;
3. scorecard:
   - autonomy
   - data usage
   - evidence quality
   - collaboration quality
   - recovery quality

Критерий завершения:
- есть повторяемая численная оценка каждого агента, а не субъективный статус.

## Phase N — Final Judge and Responsibility Graph
Цель: сделать финальную ответственность не размытой.

Сделать:
1. `VITOCore` как orchestrator, не как свободный chat router.
2. `QualityJudge` как domain scorer, не только text grader.
3. final responsibility matrix:
   - кто владелец результата
   - кто supply agent
   - кто verifier
   - кто blocker
4. `block` signals из interaction map должны реально останавливать опасные действия.

Критерий завершения:
- у каждого workflow есть lead/support/verify/block chain.

## 5. Must-have реализации из документов

Из `VITO_AGENTS_DEEP_2026.docx` брать на 100%:
- переоценку агентов по боевой готовности;
- приоритет P0/P1 uplift;
- запрет считать thin-wrapper зрелым агентом;
- усиление `BrowserAgent`, `ECommerceAgent`, `SEOAgent`, `MarketingAgent`, `EconomicsAgent`, `LegalAgent`, `RiskAgent`.

Из `VITO_INTERACTION_MAP_2026.docx` брать на 100%:
- матрицу `trigger/data/request/feedback/block`;
- 8 сквозных workflow;
- группировку агентов по operational families.

Из `VITO_IMPL_GUIDE_2026.docx` брать на 100%:
- `BaseAgent.ask(...)`
- `BaseAgent.delegate(...)`
- `registry.set_registry(...)`
- `QualityGate`
- `EventBus.emit(...)` / signal layer
- backward-compatible rollout
- quality gates и event-driven связность.

## 6. Что запрещено

- Не добавлять новые агенты, пока слабые текущие не доведены до зрелости.
- Не считать capability реализованной без benchmark.
- Не делать прямые agent-to-agent интеграции вне registry/contract layer.
- Не отмечать workflow завершенным, если связь между агентами только логируется, но не влияет на execution.

## 7. Definition of Success

Агентный слой считается доведенным только если одновременно:
- все 23 агента имеют runtime contracts и benchmarks;
- ни один агент не остался thin-wrapper в обязательной зоне ответственности;
- все 8 ключевых workflow проходят;
- map of interactions реализована как runtime graph;
- все обязательные связи либо работают, либо имеют явный documented block reason;
- VITOCore, QualityJudge и final verifier собирают систему в единый организм, а не в набор независимых LLM-вызовов.
