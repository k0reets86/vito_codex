from __future__ import annotations

from types import SimpleNamespace

from modules.platform_readiness_actions import (
    build_platform_readiness_step,
    execute_platform_readiness_action,
    parse_platform_readiness_step,
)


def test_platform_readiness_step_roundtrip() -> None:
    step = build_platform_readiness_step('reauth:etsy')
    assert step == 'platform_readiness:reauth:etsy'
    assert parse_platform_readiness_step(step) == 'reauth:etsy'


def test_reauth_action_returns_waiting_approval() -> None:
    out = execute_platform_readiness_action(service='etsy', action='reauth:etsy', blocker='missing_session')
    assert out['status'] == 'waiting_approval'
    assert out['agent'] == 'platform_readiness'
    assert 'etsy' in str(out['output']).lower()


def test_probe_action_uses_runner(monkeypatch) -> None:
    from modules import platform_readiness_actions as pra

    monkeypatch.setattr(pra, '_run_python', lambda script_rel: (True, 'ok'))
    monkeypatch.setattr(pra, '_latest_wave_report', lambda: None)
    monkeypatch.setattr(pra, '_read_json', lambda path: {'checks': [{'platform': 'etsy', 'state': 'partial'}]})
    monkeypatch.setattr(pra, '_find_service_check', lambda report, service: {'platform': service, 'state': 'partial'})
    out = execute_platform_readiness_action(service='etsy', action='run_probe:etsy')
    assert out['status'] == 'completed'
    assert out['output']['state'] == 'partial'


def test_owner_grade_validate_uses_registry(monkeypatch) -> None:
    from modules import platform_readiness_actions as pra

    calls = iter([
        {'etsy': {'state': 'partial', 'owner_grade_ok': False}},
        {'etsy': {'state': 'owner_grade', 'owner_grade_ok': True}},
    ])
    monkeypatch.setattr(pra, '_run_python', lambda script_rel: (True, 'ok'))
    monkeypatch.setattr(pra, 'load_platform_validation_registry', lambda: next(calls))
    out = execute_platform_readiness_action(service='etsy', action='owner_grade_validate:etsy')
    assert out['status'] == 'completed'
    assert out['output']['owner_grade_ok'] is True
