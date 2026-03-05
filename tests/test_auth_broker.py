from modules.auth_broker import AuthBroker


def test_auth_broker_ttl_and_status(tmp_path):
    state = tmp_path / "auth_broker_state.json"
    b = AuthBroker(state_path=str(state))
    b.mark_authenticated("etsy", method="browser_storage", detail="ok", ttl_sec=120)
    node = b.get("etsy")
    assert node["status"] == "authenticated"
    assert node["method"] == "browser_storage"
    assert node["is_valid"] is True


def test_auth_broker_clear(tmp_path):
    state = tmp_path / "auth_broker_state.json"
    b = AuthBroker(state_path=str(state))
    b.mark_authenticated("kofi", method="manual_confirmed", ttl_sec=120)
    assert b.is_authenticated("kofi") is True
    b.clear("kofi")
    assert b.is_authenticated("kofi") is False

