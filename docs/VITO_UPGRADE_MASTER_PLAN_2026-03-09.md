# VITO Upgrade Master Plan — 2026-03-09

Статус: MANDATORY
Источник:
- `input/inbox/screenshots/VITO_COMBAT_AUDIT_2026.docx`
- `input/inbox/screenshots/VITO_MEGA_RESEARCH_2026.docx`
- `input/inbox/screenshots/VITO_IMPROVEMENTS_2026.docx`
- `reports/VITO_HARD_AUDIT_2026-03-09.md`
- внешние референсы: LangGraph, Rasa, Gemini Structured Output, Anthropic Effective Agents, mem0, GPT-Researcher, CrewAI

## 0. Базовый принцип

План обязателен. От него нельзя отходить до тех пор, пока пункт не:
1. реализован в коде;
2. покрыт тестами;
3. подтвержден сценариями;
4. отражен в чеклисте.

Никакие архитектурные украшения, новые платформы и новые агенты не важнее этого плана.

## 1. Цель

Довести VITO до состояния, где он:
- понимает owner-команды через Telegram устойчиво и предсказуемо;
- превращает команду в строгий runbook, а не в свободный LLM-ответ;
- доводит платформенные задачи до полного результата без дублей и ложных done;
- хранит и применяет память как исполняемое знание;
- использует агентов как реальные автономные units, а не как thin wrappers;
- умеет самообучаться, самолечиться и безопасно апгрейдить себя;
- подтверждает успех только через proof-of-work.

## 2. Неподвижные правила

### 2.1 Никаких ложных завершений
Успех допустим только при совпадении:
- `screenshot`
- `reload`
- `DOM/state`
- `URL/public/editor view`
- `evidence contract`

### 2.2 Один объект на задачу
- Один `task_root_id`.
- Один `working_object_id` на платформу внутри задачи.
- После первого `create` -> только `update`.
- Старые опубликованные/защищенные объекты never auto-edit.

### 2.3 Никаких action-step LLM hallucinations
Для `publish/upload/post/register/pay/submit/create_listing/deploy` запрещен мягкий LLM fallback, который имитирует успех без реального действия.

## 3. Главные направления работ

## Phase A — Execution Guardrails + Final Verifier
Цель: сделать так, чтобы VITO технически не мог нарушать красное правило.

Сделать:
1. Единый `Final Verifier` над adapter -> agent -> queue -> vito_core.
2. Платформенные `Definition of Done` контракты в коде, не в тексте.
3. Hard object protection registry для всех платформ.
4. Жесткий `task_root_id` gate на reuse/update.
5. Полный запрет implicit fallback на старые existing objects.
6. `Proof-of-Work` schema для action-результатов.

Критерий завершения:
- частичный объект больше не может пройти как success;
- published/protected object не может быть тронут автоматически;
- любой platform run заканчивается только через verifier.

## Phase B — Telegram Command Compiler
Цель: убрать слабое “угадывание” и превратить TG в deterministic command layer.

Сделать:
1. Отдельный `Telegram NLU Router` как модуль.
2. `Rule-first parse` для простых и критичных случаев.
3. `Gemini 2.5 Flash` как основной быстрый parser вместо Haiku для intent/slot parsing.
4. Structured schema output:
   - intent
   - platform
   - task_family
   - selected_option
   - target_policy
   - risk_level
   - needs_confirmation
5. Fuzzy matching + typo normalization + conversation window.
6. Clarification mode при низкой уверенности.
7. Response normalization: короткие и предсказуемые ответы владельцу.

Критерий завершения:
- шумные TG-команды не ломают routing;
- ambiguous команды или route'ятся правильно, или вызывают четкое уточнение;
- TG становится compiler/runbook launcher, а не просто conversational layer.

## Phase C — Memory That Actually Governs Runtime
Цель: память должна менять поведение, а не просто хранить заметки.

Сделать:
1. Разделить memory layers окончательно:
   - owner memory
   - task memory
   - platform runbooks
   - anti-pattern memory
   - self-learning lessons
   - protected object registry
2. Превратить platform knowledge в executable runbook packs.
3. Активировать relevance/reranking everywhere.
4. Консолидировать хранилища ошибок в единый failure substrate.
5. Оценить и, если подтвердится ценность, внедрить self-hosted `mem0` как shared memory layer поверх существующей архитектуры, а не вместо нее.
6. Все lessons должны менять runtime route/gate или verifier — иначе не считаются learning outcome.

Критерий завершения:
- VITO при похожей задаче воспроизводимо выбирает уже подтвержденный путь;
- memory становится operational control plane.

## Phase D — Deep Research Engine
Цель: ResearchAgent должен делать настоящее deep research, а не 1-2 LLM-вызова.

Сделать:
1. Итеративный research loop:
   - hypotheses
   - search plan
   - multi-source retrieval
   - fact extraction
   - gap detection
   - refinement loop
   - final report + score
2. Разделить `raw research`, `synthesis`, `judge`.
3. Хранить полный research artifact в файл и memory.
4. После research выдавать:
   - top ideas
   - score 0-100
   - почему
   - recommended platforms
   - risks
   - promotion path
5. Использовать `Gemini 2.5 Flash` для cheap parsing/rough passes, боевой router оставить переключаемым.
6. Взять идеи из `gpt-researcher` и `mem0 deep research`, но адаптировать под VITO architecture.

Критерий завершения:
- VITO по команде через TG выдает не огрызок, а полноценное исследование, пригодное для product pipeline.

## Phase E — MegaBrowser 2.0
Цель: browser execution должен стать намного менее хрупким.

Сделать:
1. Browser capability map по платформам.
2. Screenshot-first execution режим как default для новых/хрупких flow.
3. Multi-profile/session isolation.
4. Humanization path и анти-бот execution layer.
5. 2FA/OTP interrupt protocol как стандарт.
6. Profile-completion runbooks, если платформа блокирует дальнейшую работу до заполнения профиля.
7. Рассмотреть `patchright`/усовершенствованный browser stack, но внедрять только после controlled verification.

Критерий завершения:
- browser failures меньше зависят от ручного “угадывания”; VITO идет по картам экрана и known save/publish paths.

## Phase F — Agent Specialization and Collaboration Map
Цель: агенты должны быть боевыми units, а не thin wrappers.

Сделать:
1. Для каждого агента закрепить:
   - owned outcomes
   - hard capabilities
   - tools
   - memory inputs
   - outputs/evidence
   - collaboration map
2. У слабых агентов (`browser_agent`, `ecommerce_agent`, `account_manager`, `vito_core`, затем `document_agent`, `hr_agent`, `devops_agent`) убрать wrapper-behavior.
3. Добавить fixed benchmark tasks по каждому агенту.
4. QualityJudge и/или final verifier должны проверять output не только по форме, но и по domain quality.
5. Агент должен уметь сам запросить поддержку у другого агента по declared collaboration map.

Критерий завершения:
- по каждому агенту можно показать не “он вызывает LLM”, а “он стабильно владеет своим operational lane”.

## Phase G — Self-Healing and Safe Upgrades
Цель: self-heal должен чинить не только кодовую мелочь, но и execution regressions.

Сделать:
1. Повторяющиеся browser/platform failures должны формировать repair candidates.
2. Ремедиации должны тестироваться в verify mode.
3. Только verified remediation может стать promoted fix.
4. DevOpsAgent и SelfHealer должны быть жестко связаны.
5. Tool allowlist должна расширяться ровно там, где это безопасно и нужно для self-heal.

Критерий завершения:
- self-heal перестает быть mostly advisory и начинает реально чинить типовые execution regressions.

## Phase H — Full Combat Validation
Цель: не считать систему готовой без боевых сценариев.

Сделать:
1. Safe regression pack.
2. Noisy TG regression pack.
3. Live owner platform pack.
4. Duplicate protection pack.
5. Protected object pack.
6. Platform DoD verifier pack.
7. 23-agent fixed benchmark audit.

Критерий завершения:
- VITO проходит не только симуляции понимания, но и реальные execution scenarios.

## 4. Что берем из предложенных материалов на 100%

Из `VITO_COMBAT_AUDIT_2026.docx`:
- убрать любые unsafe prompt костыли;
- связать self-healer и devops_agent;
- сделать requirements/bootstrap reproducible;
- убрать tracked runtime data;
- активировать relevance и consolidation в memory;
- перестать считать thin-wrapper агенты зрелыми.

Из `VITO_MEGA_RESEARCH_2026.docx`:
- Gemini 2.5 Flash как cheap parser / intent / rough-research слой;
- deep research как iterative engine;
- memory-first upgrade path через mem0 evaluation;
- browser 2.0 как отдельный пакет;
- Etsy/Gumroad/Twitter browser-first reality учесть как обязательное ограничение.

Из `VITO_IMPROVEMENTS_2026.docx`:
- TG intent router;
- fuzzy matching + context window;
- proof-of-work для action-step;
- ban LLM fallback for real-world actions;
- collaboration maps;
- stronger specialization.

## 5. Внешние референсы, которые считаем правильным вектором
- LangGraph persistence / durable execution:
  - https://docs.langchain.com/oss/python/langgraph/persistence
  - https://docs.langchain.com/oss/python/langgraph/durable-execution
- Rasa memory and flows:
  - https://rasa.com/docs/pro/build/assistant-memory/
  - https://rasa.com/docs/pro/build/writing-flows/
- Gemini structured outputs:
  - https://ai.google.dev/gemini-api/docs/structured-output
- Anthropic effective agents:
  - https://www.anthropic.com/engineering/building-effective-agents
- mem0:
  - https://github.com/mem0ai/mem0
- GPT Researcher:
  - https://github.com/assafelovic/gpt-researcher
- CrewAI patterns:
  - https://github.com/crewAIInc/crewAI

## 6. Запреты до выполнения плана
- Не расширять поверхность новыми платформами без runbook contracts.
- Не считать симуляторный успех платформенным успехом.
- Не считать notes в knowledge полноценным learning outcome.
- Не делать новые agent wrappers вместо усиления существующих weak agents.
- Не расходовать ресурсы на cosmetic UX до закрытия execution discipline.

## 7. Definition of Success
VITO можно будет считать близким к изначальному SOUL только когда одновременно выполнены все условия:
- TG понимает команды устойчиво;
- task_root и object invariants непробиваемы;
- platform runbooks формализованы и исполняемы;
- final verifier не дает ложных done;
- weak agents усилены;
- self-learning реально меняет runtime behavior;
- live combat scenarios проходят повторяемо.
