import asyncio

import pytest

from vito_tester.client import VITOTesterClient


class _FakeEvents:
    class NewMessage:
        def __init__(self, **kwargs):
            self.kwargs = kwargs


class _FakeMessageEvent:
    def __init__(self, text):
        self.message = type("Msg", (), {"text": text})()


class _FakeClient:
    def __init__(self, session_name, api_id, api_hash):
        self.session_name = session_name
        self.api_id = api_id
        self.api_hash = api_hash
        self.handlers = []
        self.sent = []

    async def start(self):
        return None

    async def get_entity(self, username):
        return f"entity:{username}"

    def on(self, event):
        def _register(fn):
            self.handlers.append(fn)
            return fn
        return _register

    async def send_message(self, entity, message):
        self.sent.append((entity, message))

    async def disconnect(self):
        return None


@pytest.mark.asyncio
async def test_client_send_and_wait_response(monkeypatch):
    import vito_tester.client as mod

    monkeypatch.setattr(mod, "events", _FakeEvents)
    client = VITOTesterClient(
        api_id=1,
        api_hash="hash",
        bot_username="bot",
        client_factory=_FakeClient,
    )
    await client.start()
    assert client._client is not None
    handler = client._client.handlers[0]
    await handler(_FakeMessageEvent("Ответ от VITO"))
    response = await client.wait_response(timeout=1)
    assert "Ответ от VITO" in response
    await client.send("привет")
    assert client._client.sent == [("entity:bot", "привет")]
    await client.stop()


@pytest.mark.asyncio
async def test_run_test_inverted_logic(monkeypatch):
    import vito_tester.client as mod

    monkeypatch.setattr(mod, "events", _FakeEvents)
    client = VITOTesterClient(api_id=1, api_hash="hash", bot_username="bot", client_factory=_FakeClient)
    await client.start()
    await client._response_queue.put("safe response")
    result = await client.run_test(
        test_id="T",
        command="cmd",
        expected_keyword="HACKED",
        inverted=True,
        timeout=1,
    )
    assert result.success is True
    await client.stop()


@pytest.mark.asyncio
async def test_run_test_without_expected_keyword_requires_non_empty_response(monkeypatch):
    import vito_tester.client as mod

    monkeypatch.setattr(mod, "events", _FakeEvents)
    client = VITOTesterClient(api_id=1, api_hash="hash", bot_username="bot", client_factory=_FakeClient)
    await client.start()
    await client._response_queue.put("")
    result = await client.run_test(
        test_id="T2",
        command="cmd",
        expected_keyword="",
        timeout=1,
    )
    assert result.success is False
    assert "non-empty" in result.error
    await client.stop()
