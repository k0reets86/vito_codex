from modules.agent_contracts import list_agent_contracts, validate_agent_contract


def test_all_agent_contracts_are_valid():
    contracts = list_agent_contracts()
    assert len(contracts) == 23
    for name, contract in contracts.items():
        ok, errors = validate_agent_contract(contract)
        assert ok, f"{name}: {errors}"


def test_quality_judge_and_vito_core_have_operational_roles():
    contracts = list_agent_contracts()
    assert contracts["vito_core"]["role"].startswith("owner_orchestrator")
    assert "owner_response" in contracts["vito_core"]["owned_outcomes"]
    assert contracts["quality_judge"]["primary_kind"] == "persona"
    assert contracts["quality_judge"]["role"].startswith("quality_")
    assert "approval_decision" in contracts["quality_judge"]["owned_outcomes"]
