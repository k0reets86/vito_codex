# Owner Preference Model Spec v1 (2026-02-25)

## Goals
- Make VITO learn the owner's priorities, constraints, and style reliably.
- Ensure preferences are explicit, auditable, and controllable by the owner.

## Preference Blocks
- `priorities`: ROI focus, speed vs quality, risk tolerance
- `constraints`: budget thresholds, legal/safety limits
- `style`: language, verbosity, tone, format
- `channels`: preferred platforms and tools
- `schedule`: time windows, reporting cadence

## Default Seeds (Optional)
Use `scripts/seed_preference_blocks.py` to seed minimal defaults if missing.

## Commands
- Set: `/pref key=value`
- Deactivate: `/pref_del key` or `forget key` / `забыть key`
- List: `/prefs`

## Auto-Detect (Optional)
- Disabled by default via `OWNER_PREF_AUTO_DETECT=false`.
- If enabled, can log weak signals like “пиши кратко” → `style.verbosity=concise`.

## Eval Script
Use `scripts/owner_pref_eval.py` to print current prefs summary.

## Storage
- SQLite `owner_preferences`
- Events table `owner_preference_events`
- Semantic sync to Chroma as `owner_preference`

## Metrics
- `active_prefs`
- `set_events`
- `use_events`
- `last_updated`

## Safety
- Owner can deactivate any preference.
- Preferences never execute unsafe actions without existing policy/approval gates.
