from modules.agent_contracts import get_agent_contract
from modules.agent_runtime_verifier import validate_agent_runtime_contract


def test_agent_runtime_verifier_accepts_browser_output_with_required_evidence():
    contract = get_agent_contract("browser_agent", ["browse"], "browser")
    chk = validate_agent_runtime_contract(
        agent_name="browser_agent",
        task_type="browse",
        output={"url": "https://example.com", "verified": True, "screenshot_path": "runtime/shot.png"},
        metadata={"collaboration_contract": {"collaborates_with": ["account_manager"]}},
        contract=contract,
        orchestration_plan={},
    )
    assert chk.ok is True


def test_agent_runtime_verifier_rejects_browser_output_without_screenshot():
    contract = get_agent_contract("browser_agent", ["browse"], "browser")
    chk = validate_agent_runtime_contract(
        agent_name="browser_agent",
        task_type="browse",
        output={"url": "https://example.com", "verified": True},
        metadata={"collaboration_contract": {"collaborates_with": ["account_manager"]}},
        contract=contract,
        orchestration_plan={},
    )
    assert chk.ok is False
    assert "missing_required_evidence:screenshot_or_trace" in chk.errors


def test_agent_runtime_verifier_accepts_account_manager_structured_output():
    contract = get_agent_contract("account_manager", ["account_management"], "account")
    chk = validate_agent_runtime_contract(
        agent_name="account_manager",
        task_type="account_management",
        output={"account": "etsy", "auth_state": "configured"},
        metadata={"collaboration_contract": {"collaborates_with": ["browser_agent", "ecommerce_agent"]}},
        contract=contract,
        orchestration_plan={},
    )
    assert chk.ok is True
