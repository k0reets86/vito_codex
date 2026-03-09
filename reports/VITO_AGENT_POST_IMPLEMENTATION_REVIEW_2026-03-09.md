# VITO Agent Post-Implementation Review — 2026-03-09

Источник:
- `reports/VITO_AGENT_BENCHMARK_MATRIX_2026-03-09_2333UTC.json`
- `docs/VITO_AGENT_IMPLEMENTATION_CHECKLIST_2026-03-09.md`

## Итог

Агентный план `Phase I-N` завершен, но это не означает, что агентный слой достиг целевого уровня `9+/10`.

Текущая честная оценка по матрице:
- `benchmark_matrix_score = 6.89 / 10`

Сильные стороны:
- Все `23/23` агентов теперь проходят единый benchmark-контур.
- У всех есть:
  - runtime contract,
  - skill/runtime profile,
  - collaboration context,
  - evidence-bearing output path.
- Workflow substrate и responsibility graph работают как единый runtime-слой, а не как описание в документах.

Главная проблема:
- Система перестала быть "thin-wrapper jungle", но еще не стала железным автономным агентным роем.
- Главный недобор теперь не в наличии агентов, а в **глубине их operational behavior**.

## Оценки по семействам

- `core_control`: `7.26`
- `intelligence_research`: `6.92`
- `governance_resilience`: `6.88`
- `content_growth`: `6.81`
- `commerce_execution`: `6.75`

## Почему оценки ниже желаемых

### 1. Recovery quality остается главным тормозом

Самый слабый показатель почти во всех семействах:
- `commerce_execution.recovery_quality = 4.03`
- `content_growth.recovery_quality = 2.54`
- `intelligence_research.recovery_quality = 2.80`

Это означает:
- агент умеет выполнить задачу;
- агент умеет вернуть structured output;
- но агент еще недостаточно хорошо:
  - распознает сбой как типовой,
  - подбирает корректный следующий маршрут,
  - эскалирует по declared graph,
  - повторно входит в задачу без деградации качества.

### 2. Data usage еще слишком средний

Часть агентов уже имеет реальные tool/data paths, но глубина разная.

Особенно проседают:
- `translation_agent.data_usage = 4.47`
- `account_manager.data_usage = 5.52`
- `legal_agent.data_usage = 5.85`

Это не thin-wrapper, но еще и не "агент с богатой operational базой".

### 3. Collaboration есть, но не везде outcome-changing

Collaboration map и runtime handoff есть, но часть агентов все еще:
- формально знает, с кем работать;
- но не меняет результат так сильно, как должен по взрослой multi-agent системе.

### 4. Commerce слой штрафуется строже всего

`commerce_execution` ниже не потому, что там все плохо, а потому что там:
- самые строгие proof-of-work требования,
- реальные внешние платформы,
- fail-closed verifier,
- auth/browser/platform edges.

Это честный штраф за боевой слой.

## Кто тянет оценку вниз сильнее всего

### Критический нижний слой

1. `browser_agent` — `5.91`
- главная проблема: `recovery_quality = 2.13`
- это все еще главный нестабильный узел внешнего исполнения

2. `translation_agent` — `6.14`
- проблема: низкий `data_usage`, слабый `recovery`

3. `economics_agent` — `6.37`
- проблема: operational depth еще недостаточна, слишком мало реального рыночного сигнала

4. `account_manager` — `6.41`
- проблема: auth-state есть, но adaptive recovery/auth handoff еще недостаточно зрелые

5. `legal_agent` — `6.44`
- проблема: policy/runbook depth все еще недостаточны для реальной platform gating работы

### Второй слой риска

6. `partnership_agent` — `6.53`
7. `document_agent` — `6.67`
8. `marketing_agent` — `6.86`
9. `risk_agent` — `6.86`
10. `trend_scout` — `6.87`

## Что уже реально хорошо

### Сильные агенты текущего цикла

- `ecommerce_agent` — `7.62`
- `content_creator` — `7.40`
- `hr_agent` — `7.40`
- `vito_core` — `7.28`
- `quality_judge` — `7.11`

Это не идеал, но это уже реальные operational units.

## Жесткий вывод

Переход от "агенты как прослойки" к "агенты как units" выполнен.

Но следующий разрыв теперь другой:
- не "агентов нет",
- а "агенты еще недостаточно глубоко умеют восстанавливаться, обмениваться operational state и использовать data/tool paths как primary lane".

Следующий этап улучшения должен быть направлен не на расширение количества агентов, а на:
- recovery depth,
- richer tool/data packs,
- stronger cross-agent outcome dependence,
- benchmark-driven uplift weakest agents first.
