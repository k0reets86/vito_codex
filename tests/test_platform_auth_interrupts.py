from modules.platform_auth_interrupts import PlatformAuthInterrupts


def test_platform_auth_interrupts_raise_and_resolve(tmp_path):
    reg = PlatformAuthInterrupts(tmp_path / "auth_interrupts.db")
    iid = reg.raise_interrupt("etsy", "missing_session", detail="reauth:etsy")
    assert iid > 0
    pending = reg.list_interrupts(status="pending")
    assert len(pending) == 1
    assert pending[0]["service"] == "etsy"
    assert pending[0]["blocker"] == "missing_session"
    assert reg.resolve_interrupt("etsy") == 1
    assert reg.list_interrupts(status="pending") == []
