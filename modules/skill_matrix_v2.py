"""Skill Matrix v2 поверх agent contracts.

Матрица больше не собирается только из эвристик по capability.
Её источник правды — единый operational contract агента.
"""

from __future__ import annotations

from typing import Any

from modules.agent_contracts import get_agent_contract, validate_agent_contract


def build_agent_skill_matrix_v2(agent_name: str, capabilities: list[str], description: str = "") -> dict[str, Any]:
    return get_agent_contract(agent_name=agent_name, capabilities=capabilities, description=description)


def validate_agent_skill_matrix_v2(row: dict[str, Any]) -> tuple[bool, list[str]]:
    return validate_agent_contract(row)
