from config.agent_benchmark_tasks import AGENT_BENCHMARK_TASKS
from modules.agent_contracts import list_agent_contracts


def test_agent_benchmark_tasks_cover_all_contract_agents():
    contracts = list_agent_contracts()
    assert set(contracts.keys()) == set(AGENT_BENCHMARK_TASKS.keys())
    for agent_name, tasks in AGENT_BENCHMARK_TASKS.items():
        assert isinstance(tasks, list) and tasks, agent_name
        for task in tasks:
            assert str(task.get("capability") or "").strip(), agent_name
            assert str(task.get("task") or "").strip(), agent_name
