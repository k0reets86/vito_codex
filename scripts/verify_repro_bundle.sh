#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[verify] repo root: $ROOT_DIR"

missing=0

require_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    echo "[ok] file: $path"
  else
    echo "[missing] file: $path"
    missing=1
  fi
}

require_dir() {
  local path="$1"
  if [[ -d "$path" ]]; then
    echo "[ok] dir: $path"
  else
    echo "[missing] dir: $path"
    missing=1
  fi
}

require_file "Dockerfile"
require_file "docker-compose.yml"
require_file "requirements.txt"
require_file ".env.example"
require_file "docs/DEPLOY_REPRODUCIBLE_SETUP.md"
require_file "main.py"
require_dir "scripts"

python3 - <<'PY'
import importlib.util
mods = ["dotenv", "playwright"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
if missing:
    print(f"[warn] python modules missing in current environment: {', '.join(missing)}")
else:
    print("[ok] python modules: dotenv, playwright")
PY

if command -v docker >/dev/null 2>&1; then
  echo "[ok] docker binary found"
else
  echo "[warn] docker binary not found in current environment"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "[ok] docker compose available"
else
  echo "[warn] docker compose not available in current environment"
fi

if [[ "$missing" -ne 0 ]]; then
  echo "[fail] reproducible bundle is incomplete"
  exit 1
fi

echo "[ok] reproducible bundle baseline is present"
