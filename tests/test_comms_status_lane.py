from modules.comms_status_lane import render_platforms_hub_with_readiness, render_unified_status


def test_render_platforms_hub_with_readiness_smoke(monkeypatch):
    import modules.comms_status_lane as lane
    monkeypatch.setattr(lane, 'assess_platform_readiness', lambda: [
        {'service': 'etsy', 'owner_grade_state': 'owner_grade', 'can_validate_now': True, 'blocker': '', 'recommended_action': '', 'reauth_command': ''}
    ])
    text = render_platforms_hub_with_readiness()
    assert 'Платформы' in text
    assert 'owner-grade=1' in text


def test_render_unified_status_smoke():
    class DummyLoop:
        def get_status(self):
            return {'running': True, 'tick_count': 1, 'daily_spend': 0, 'platform_readiness': {'total': 0, 'owner_grade': 0, 'can_validate_now': 0, 'blocked': 0, 'next_steps': []}}
    text = render_unified_status(title='X', decision_loop=DummyLoop(), pending_approvals_count=0)
    assert 'X' in text
