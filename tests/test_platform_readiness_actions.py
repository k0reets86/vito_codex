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
    assert int(out['output']['platform_auth_interrupt_id']) > 0


def test_probe_action_uses_runner(monkeypatch) -> None:
    from modules import platform_readiness_actions as pra

    monkeypatch.setattr(pra, '_run_python', lambda script_rel: (True, 'ok'))
    monkeypatch.setattr(pra, '_latest_wave_report', lambda: None)
    monkeypatch.setattr(pra, '_read_json', lambda path: {'checks': [{'platform': 'etsy', 'state': 'partial'}]})
    monkeypatch.setattr(pra, '_find_service_check', lambda report, service: {'platform': service, 'state': 'partial'})
    out = execute_platform_readiness_action(service='etsy', action='run_probe:etsy')
    assert out['status'] == 'completed'
    assert out['output']['state'] == 'partial'


def test_probe_action_missing_session_raises_interrupt(monkeypatch) -> None:
    from modules import platform_readiness_actions as pra

    called = {'raised': False}
    monkeypatch.setattr(pra, '_run_python', lambda script_rel: (True, 'signin'))
    monkeypatch.setattr(pra, '_latest_wave_report', lambda: None)
    monkeypatch.setattr(pra, '_read_json', lambda path: {'checks': [{'platform': 'etsy', 'state': 'blocked', 'blocker': 'missing_session'}]})
    monkeypatch.setattr(pra, '_find_service_check', lambda report, service: {'platform': service, 'state': 'blocked', 'blocker': 'missing_session'})

    class _Interrupts:
        def raise_interrupt(self, service, blocker, detail=''):
            called['raised'] = (service, blocker, detail)
            return 1
        def resolve_interrupt(self, service):
            return 0
    monkeypatch.setattr(pra, 'PlatformAuthInterrupts', _Interrupts)

    out = execute_platform_readiness_action(service='etsy', action='run_probe:etsy')
    assert out['status'] == 'completed'
    assert called['raised'][0] == 'etsy'
    assert called['raised'][1] == 'missing_session'


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


def test_owner_grade_validate_missing_session_raises_interrupt(monkeypatch) -> None:
    from modules import platform_readiness_actions as pra

    called = {'raised': False}
    monkeypatch.setattr(pra, '_run_python', lambda script_rel: (True, 'signin'))
    calls = iter([
        {'etsy': {'state': 'partial', 'owner_grade_ok': False}},
        {'etsy': {'state': 'blocked', 'owner_grade_ok': False, 'blocker': 'missing_session'}},
    ])
    monkeypatch.setattr(pra, 'load_platform_validation_registry', lambda: next(calls))

    class _Interrupts:
        def raise_interrupt(self, service, blocker, detail=''):
            called['raised'] = (service, blocker, detail)
            return 1
        def resolve_interrupt(self, service):
            return 0
    monkeypatch.setattr(pra, 'PlatformAuthInterrupts', _Interrupts)

    out = execute_platform_readiness_action(service='etsy', action='owner_grade_validate:etsy')
    assert out['status'] == 'completed'
    assert called['raised'][0] == 'etsy'
    assert called['raised'][1] == 'missing_session'


def test_reauth_action_returns_capture_command() -> None:
    out = execute_platform_readiness_action(service='twitter', action='reauth:twitter', blocker='missing_session')
    payload = out['output']
    assert payload['reauth_command'].startswith('python3 scripts/browser_auth_capture.py twitter')
    assert 'twitter_storage_state.json' in str(payload['storage_state_path'])
    assert 'browser_profiles' in str(payload['persistent_profile_dir'])



def test_assess_platform_readiness_includes_reauth_command(monkeypatch):
    from modules import platform_readiness as pr
    monkeypatch.setattr(pr, 'load_service_sessions', lambda: {})
    monkeypatch.setattr(pr, '_wave_state_map', lambda: {})
    monkeypatch.setattr(pr, 'load_platform_validation_registry', lambda: {})
    monkeypatch.setattr(pr, '_probe_exists', lambda service: False)
    row = next(x for x in pr.assess_platform_readiness(['twitter']) if x['service'] == 'twitter')
    assert row['blocker'] == 'missing_session'
    assert row['reauth_command'].startswith('python3 scripts/browser_auth_capture.py twitter')
    assert 'twitter_storage_state.json' in row['storage_state_path']


def test_assess_platform_readiness_twitter_api_mode_not_missing_session(monkeypatch):
    from modules import platform_readiness as pr
    monkeypatch.setattr(pr, 'load_service_sessions', lambda: {})
    monkeypatch.setattr(pr, '_wave_state_map', lambda: {'twitter': 'partial'})
    monkeypatch.setattr(pr, 'load_platform_validation_registry', lambda: {})
    monkeypatch.setattr(pr, '_probe_exists', lambda service: service == 'twitter')
    monkeypatch.setattr(pr.settings, 'TWITTER_MODE', 'api')
    monkeypatch.setattr(pr.settings, 'TWITTER_CONSUMER_KEY', 'ck')
    monkeypatch.setattr(pr.settings, 'TWITTER_CONSUMER_SECRET', 'cs')
    monkeypatch.setattr(pr.settings, 'TWITTER_ACCESS_TOKEN', 'at')
    monkeypatch.setattr(pr.settings, 'TWITTER_ACCESS_SECRET', 'as')
    row = next(x for x in pr.assess_platform_readiness(['twitter']) if x['service'] == 'twitter')
    assert row['blocker'] == ''
    assert row['can_validate_now'] is True
    assert row['recommended_action'] == 'owner_grade_validate:twitter'



def test_reauth_action_auto_success(monkeypatch):
    from modules import platform_readiness_actions as pra
    monkeypatch.setattr(pra, '_attempt_auto_reauth', lambda svc: (True, 'ok', {'auto_attempted': True, 'auto_reauth_ok': True}))
    out = pra.execute_platform_readiness_action(service='etsy', action='reauth:etsy', blocker='missing_session')
    assert out['status'] == 'completed'
    assert out['output']['state'] == 'session_restored'
    assert out['output']['auto_reauth_ok'] is True


def test_reauth_action_auto_challenge_falls_back(monkeypatch):
    from modules import platform_readiness_actions as pra
    monkeypatch.setattr(pra, '_attempt_auto_reauth', lambda svc: (False, 'OTP_REQUIRED: challenge', {'auto_attempted': True, 'auto_reauth_ok': False, 'auto_reauth_blocker': 'challenge'}))
    out = pra.execute_platform_readiness_action(service='etsy', action='reauth:etsy', blocker='missing_session')
    assert out['status'] == 'waiting_approval'
    assert out['output']['auto_reauth_blocker'] == 'challenge'


def test_printful_reauth_action_auto_success(monkeypatch):
    from modules import platform_readiness_actions as pra
    monkeypatch.setattr(pra, '_attempt_auto_reauth', lambda svc: (True, 'ok', {'auto_attempted': True, 'auto_reauth_ok': True}))
    out = pra.execute_platform_readiness_action(service='printful', action='reauth:printful', blocker='missing_session')
    assert out['status'] == 'completed'
    assert out['output']['state'] == 'session_restored'
    assert out['output']['auto_reauth_ok'] is True
