# VITO Acceptance Command Matrix (Owner-Facing)

## Purpose
Deterministic acceptance checks for natural-language owner commands.
Pass criteria: correct routing + concrete evidence in output.

## Legend
- `Route`: expected primary subsystem.
- `Evidence`: required proof artifact in response/logs.
- `Result`: `PASS/FAIL` during live test run.

| # | Owner Command (natural language) | Route | Evidence Required | Result |
|---|---|---|---|---|
| 1 | `найди тренды цифровых продуктов для gumroad` | `conversation_engine -> scan_trends` | action output with `[scan_trends][status=completed]` + trend summary | PASS (auto, `tests/test_acceptance_command_matrix.py`) |
| 2 | `какая сейчас статистика на гумроад` | `conversation_engine -> sales_check(gumroad)` | `sales/revenue/products_count` in response | PASS (auto, `tests/test_acceptance_command_matrix.py`) |
| 3 | `проверь доступ к интернету` | `conversation_engine -> network_utils.basic_net_report` | per-host DNS status lines + overall status | PASS (auto, `tests/test_acceptance_command_matrix.py`) |
| 4 | `покажи статус и активные задачи` | `conversation_engine quick status` | loop status + goals counters + active owner task | PASS (auto, `tests/test_acceptance_command_matrix.py`) |
| 5 | `сделай отчет по текущим задачам` | `goal_request` | created goal + visible in `/tasks`/`/goals` | PASS (auto, `tests/test_conversation_engine.py`) |
| 6 | `открой https://... и вытащи текст` | `browser_agent:web_scrape` | extracted text preview from page | PASS (auto, `tests/test_acceptance_command_matrix.py`) |
| 7 | `сделай скрин https://...` | `browser_agent:screenshot` | screenshot file path + file exists | PASS (auto, `tests/test_acceptance_command_matrix.py`) |
| 8 | `меня зовут <name>; как меня зовут?` | `owner profile memory` | correct name recall from memory | PASS (auto, `tests/test_conversation_engine.py`) |
| 9 | `измени приоритет цели <id> на high` | `change_priority` | action status completed + updated goal priority | PASS (auto, `tests/test_acceptance_command_matrix.py`) |
| 10 | `проверь ошибки системы` | `check_errors` | unresolved/resolved counts | PASS (auto, `tests/test_acceptance_command_matrix.py`) |

## Hard Fail Conditions
- Returns vague response without route execution for deterministic commands.
- Claims completion without evidence/status markers.
- Forgets explicit owner profile fact in same/next session.
- Requires repeated confirmation for safe read-only operations.
