import pytest

from agents.base_agent import TaskResult
from modules.web_operator_pack import WebOperatorPack


class _Registry:
    async def dispatch(self, task_type: str, **kwargs):
        return TaskResult(
            success=True,
            output={
                "url": "https://example.com/account",
                "screenshot_path": "/tmp/webop_test.png",
                "task_type": task_type,
            },
        )


@pytest.mark.asyncio
async def test_web_operator_pack_list_and_run(tmp_path, monkeypatch):
    # isolate sqlite for execution facts
    import modules.web_operator_pack as wp
    from config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "SQLITE_PATH", str(tmp_path / "vito.db"))

    pack = WebOperatorPack(_Registry())
    names = pack.list_scenarios()
    assert "generic_email_signup" in names
    out = await pack.run("generic_email_signup", overrides={"url": "https://example.com/signup"})
    assert out["status"] == "success"
    assert out["scenario"] == "generic_email_signup"


@pytest.mark.asyncio
async def test_web_operator_pack_unknown():
    pack = WebOperatorPack(_Registry())
    out = await pack.run("missing_scenario", overrides={})
    assert out["status"] == "error"
