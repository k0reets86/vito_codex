#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "/home/vito/vito-agent"

# Legacy backlog can be reduced over time; new occurrences are blocked in CI.
ALLOWLIST = {
    "agents/devops_agent.py",
    "agents/publisher_agent.py",
    "agents/smm_agent.py",
    "agents/vito_core.py",
    "dashboard.py",
    "dashboard_server.py",
    "knowledge_updater.py",
    "modules/fact_gate.py",
    "modules/final_scorecard.py",
    "modules/platform_knowledge.py",
    "modules/publish_contract.py",
    "modules/runtime_remediation.py",
    "modules/self_learning_test_runner.py",
    "modules/skill_registry.py",
}


def iter_py_files() -> list[Path]:
    files: list[Path] = []
    for folder in ("agents", "platforms", "modules", "config"):
        root = PROJECT_ROOT / folder
        if not root.exists():
            continue
        files.extend(root.rglob("*.py"))
    files.extend([PROJECT_ROOT / "main.py", PROJECT_ROOT / "comms_agent.py", PROJECT_ROOT / "decision_loop.py", PROJECT_ROOT / "financial_controller.py"])
    return [p for p in files if p.exists()]


def main() -> int:
    errors: list[str] = []
    for path in iter_py_files():
        rel = str(path.relative_to(PROJECT_ROOT))
        text = path.read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN in text and rel not in ALLOWLIST:
            errors.append(rel)

    if errors:
        print("Hardcoded project-root paths found in non-allowlisted files:")
        for item in sorted(errors):
            print(f"- {item}")
        return 1

    print("Hardcoded path check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
