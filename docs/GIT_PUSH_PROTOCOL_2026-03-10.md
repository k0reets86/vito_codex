# Git Push Protocol

Обязательный порядок перед каждым `git push`:

1. Проверить, что в рабочем дереве нет случайного runtime-мусора.
2. Прогнать локальный CI-гейт:

```bash
scripts/prepush_ci_gate.sh
```

3. Только после зеленого результата делать `git push`.
4. Если GitHub Actions после этого красный:
   - сначала снять точный failing step;
   - воспроизвести его локально тем же набором;
   - исправить причину;
   - снова прогнать `scripts/prepush_ci_gate.sh`;
   - только потом пушить.

Чтобы хук работал автоматически:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push scripts/prepush_ci_gate.sh
```

Что покрывает локальный CI-гейт:
- `scripts/check_hardcoded_paths.py`
- `tests/test_decision_loop.py`
- `tests/test_workflow_state_machine.py`
- `tests/test_workflow_threads.py`
- `tests/test_comms_agent.py`
- `tests/test_conversation_engine.py`
- `tests/test_memory_manager.py`
- `tests/test_vito_core.py`

Это должен быть точный минимум, который обязан быть зеленым до любого push в `main`.
