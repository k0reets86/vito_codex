from modules.skill_matrix_v2 import (
    VALID_SKILL_KINDS,
    build_agent_skill_matrix_v2,
    validate_agent_skill_matrix_v2,
)


def test_skill_matrix_v2_row_is_valid():
    row = build_agent_skill_matrix_v2(
        agent_name="research_agent",
        capabilities=["research", "market_analysis"],
        description="Research specialist",
    )
    ok, errors = validate_agent_skill_matrix_v2(row)
    assert ok is True
    assert errors == []
    assert row["primary_kind"] in VALID_SKILL_KINDS
    assert "recipe.research_pipeline" in row["recipe"]

