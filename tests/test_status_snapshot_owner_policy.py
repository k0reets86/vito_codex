from __future__ import annotations

from modules.status_snapshot import build_status_snapshot, render_status_snapshot


def test_status_snapshot_includes_owner_policy_summary(monkeypatch):
    import modules.status_snapshot as snap_mod

    monkeypatch.setattr(
        snap_mod,
        'build_owner_policy_pack',
        lambda refresh=False: {
            'active_rule_count': 3,
            'reminders': ['Не сужать объем задачи', 'Старые объекты не трогать'],
        },
    )
    snap = build_status_snapshot()
    text = render_status_snapshot(snap)
    assert 'Owner policy: активных правил 3' in text
    assert 'Не сужать объем задачи' in text
