# VITO Attachments Consolidated Plan — 2026-03-10

Источники:
- `input/attachments/VITO PLATFORM ONBOARDING.docx`
- `input/attachments/VITO STEALTH BROWSER 2026 2.docx`

Правило:
- объем требований не сокращать;
- пересечения объединять один раз;
- уже реализованное считать `done` только при наличии кода и тестов;
- недопустимые части помечать как `blocked_policy`, а не замалчивать.

## 1. Platform Onboarding

Цель:
- одна команда владельца должна запускать полный 7-фазный pipeline:
  1. research
  2. integration method
  3. owner report/decision
  4. account setup
  5. profile completion
  6. first listing test
  7. platform activation in VITO

Что уже реализовано:
- `PlatformOnboardingAgent`
- `PlatformResearcher`
- `IntegrationDetector`
- `PlatformRegistrar`
- `PlatformRegistry`
- TG routing `research_platform` / `onboard_platform`
- `PlatformProfile` persistence
- owner report/result persistence

Что осталось обязательно довести:
- owner-facing onboarding validation runner
- first-listing owner-grade proof pack
- event emission/runtime registration audit report

## 2. Human Browser Runtime

Цель:
- единый browser runtime для реальных platform adapters:
  - service-aware profiles
  - persistent sessions
  - humanized pacing
  - screenshot-first
  - LLM navigation fallback

Что уже реализовано:
- `HumanBrowser`
- `patchright` runtime path
- service-aware browser policy
- rollout в `etsy`, `gumroad`, `printful`
- browser agent backend selection

Что осталось обязательно довести:
- safe browser diagnostics runner
- targeted adapter regressions с persisted reports
- owner-grade browser validation summary

Что не реализуется в этом контуре:
- целенаправленный обход антибот-защиты, fingerprint spoofing для bypass и solver stack для обхода ограничений.
- Это отмечается как `blocked_policy`.

## 3. Порядок добивки

### P1
- синхронизация плана/чеклиста по двум документам
- owner report/result persistence
- cleanup path/trace хвостов

### P2
- safe browser diagnostics runner
- adapter regressions
- owner-grade browser validation reports

### P3
- onboarding validation runner
- first-listing proof pack
- final consolidated rerun
