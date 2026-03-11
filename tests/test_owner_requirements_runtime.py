from __future__ import annotations

from modules import owner_requirements_runtime as ort
from modules.owner_policy_packs import build_owner_policy_pack


def test_owner_requirements_runtime_extracts_core_flags(tmp_path, monkeypatch):
    log = tmp_path / 'OWNER_REQUIREMENTS_LOG.md'
    cache = tmp_path / 'owner_requirements_runtime.json'
    log.write_text(
        """
## Hard Rules
- Не сужать объем задачи без явного разрешения.
- Старые и опубликованные объекты не трогай без target id.
- Один объект на платформу, не плодить лишние дубликаты.
- Результат подтверждать скринами и reload.
- Не спамить владельцу.
- Не останавливаться на полпути.
""",
        encoding='utf-8',
    )
    monkeypatch.setattr(ort, 'LOG_PATH', log)
    monkeypatch.setattr(ort, 'CACHE_PATH', cache)
    data = ort.sync_owner_requirements_runtime()
    flags = data['flags']
    assert flags['do_not_reduce_scope'] is True
    assert flags['do_not_touch_old_or_published'] is True
    assert flags['one_object_per_platform'] is True
    assert flags['proof_required'] is True
    assert flags['quiet_execution'] is True
    assert flags['continuous_until_done'] is True


def test_owner_policy_pack_uses_runtime_cache(tmp_path, monkeypatch):
    log = tmp_path / 'OWNER_REQUIREMENTS_LOG.md'
    cache = tmp_path / 'owner_requirements_runtime.json'
    log.write_text(
        """
## Rules
- Не сужать объем задачи.
- Не трогай старое.
""",
        encoding='utf-8',
    )
    monkeypatch.setattr(ort, 'LOG_PATH', log)
    monkeypatch.setattr(ort, 'CACHE_PATH', cache)
    ort.sync_owner_requirements_runtime()
    pack = build_owner_policy_pack(refresh=False)
    assert pack['active_rule_count'] >= 2
    assert pack['flags']['do_not_reduce_scope'] is True
    assert pack['flags']['do_not_touch_old_or_published'] is True
