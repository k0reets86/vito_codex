#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONDONTWRITEBYTECODE=1

echo "[prepush] hardcoded path check"
python3 scripts/check_hardcoded_paths.py

echo "[prepush] decision/workflow critical suite"
pytest -q -c /dev/null \
  tests/test_decision_loop.py \
  tests/test_workflow_state_machine.py \
  tests/test_workflow_threads.py

echo "[prepush] comms/conversation/memory/core critical suite"
pytest -q -c /dev/null \
  tests/test_comms_agent.py \
  tests/test_conversation_engine.py \
  tests/test_memory_manager.py \
  tests/test_vito_core.py

echo "[prepush] OK"
