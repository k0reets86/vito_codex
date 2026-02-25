from modules.fact_gate import gate_outgoing_claim


def test_fact_gate_passes_normal_text():
    d = gate_outgoing_claim("План готов, запускаю выполнение.")
    assert d.allowed


def test_fact_gate_blocks_risky_claim_without_evidence(monkeypatch):
    class _F:
        def has_publish_evidence_recent(self, hours=24):
            return False

    monkeypatch.setattr("modules.fact_gate.ExecutionFacts", lambda: _F())
    d = gate_outgoing_claim("Продукт опубликован на Gumroad успешно.")
    assert not d.allowed
    assert "не подтверждённый факт" in d.text.lower()


def test_fact_gate_allows_risky_claim_with_inline_url():
    d = gate_outgoing_claim("Продукт опубликован: https://example.com/p/1")
    assert d.allowed
