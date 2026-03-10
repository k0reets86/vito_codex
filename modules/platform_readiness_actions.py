from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT
from config.settings import settings
from modules.account_auth_remediation import build_auth_remediation
from modules.platform_auth_interrupts import PlatformAuthInterrupts
from modules.platform_validation_registry import load_platform_validation_registry


def build_platform_readiness_step(action: str) -> str:
    return f"platform_readiness:{str(action or '').strip()}"


def parse_platform_readiness_step(step: str) -> str:
    s = str(step or '').strip()
    prefix = 'platform_readiness:'
    if s.startswith(prefix):
        return s[len(prefix):].strip()
    return ''


def _latest_wave_report() -> Path | None:
    files = sorted((PROJECT_ROOT / 'reports').glob('VITO_PLATFORM_LIVE_VALIDATION_WAVE_*.json'))
    return files[-1] if files else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _find_service_check(report: dict[str, Any], service: str) -> dict[str, Any]:
    for item in list(report.get('checks') or []):
        if isinstance(item, dict) and str(item.get('platform') or '').strip().lower() == service:
            return item
    return {}


def _run_python(script_rel: str) -> tuple[bool, str]:
    script = PROJECT_ROOT / script_rel
    if not script.exists():
        return False, f'missing_script:{script_rel}'
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=int(getattr(settings, 'PLATFORM_READINESS_SCRIPT_TIMEOUT_SEC', 180) or 180),
    )
    detail = (proc.stdout or proc.stderr or '').strip()[:500]
    return proc.returncode == 0, detail


def execute_platform_readiness_action(
    *,
    service: str,
    action: str,
    blocker: str = '',
) -> dict[str, Any]:
    svc = str(service or '').strip().lower()
    act = str(action or '').strip()
    block = str(blocker or '').strip()
    if not svc or not act:
        return {'status': 'failed', 'error': 'invalid_platform_readiness_action', 'agent': 'platform_readiness'}

    if act.startswith('reauth:'):
        interrupt_id = PlatformAuthInterrupts().raise_interrupt(svc, block or 'missing_session', detail=act)
        remediation = build_auth_remediation(svc, error=block or 'missing_session', configured=True)
        return {
            'status': 'waiting_approval',
            'error': f'Нужна повторная авторизация для {svc}',
            'output': {**remediation, 'platform_auth_interrupt_id': interrupt_id},
            'agent': 'platform_readiness',
        }

    if act.startswith('run_probe:'):
        ok, detail = _run_python('scripts/platform_live_validation_wave.py')
        report = _read_json(_latest_wave_report()) if _latest_wave_report() else {}
        check = _find_service_check(report, svc)
        state = str(check.get('state') or '').strip().lower()
        if ok and state in {'partial', 'owner_grade'}:
            PlatformAuthInterrupts().resolve_interrupt(svc)
        if ok and check:
            return {
                'status': 'completed',
                'output': {'service': svc, 'action': act, 'state': state or 'unknown', 'check': check},
                'agent': 'platform_readiness',
            }
        return {
            'status': 'failed',
            'error': detail or f'probe_failed:{svc}',
            'output': {'service': svc, 'action': act, 'state': state or 'unknown', 'check': check},
            'agent': 'platform_readiness',
        }

    if act.startswith('owner_grade_validate:'):
        registry_before = dict(load_platform_validation_registry().get(svc) or {})
        ok, detail = _run_python('scripts/platform_live_validation_wave.py')
        registry_after = dict(load_platform_validation_registry().get(svc) or {})
        state = str(registry_after.get('state') or registry_before.get('state') or '').strip().lower()
        owner_grade_ok = bool(registry_after.get('owner_grade_ok'))
        if ok and owner_grade_ok:
            PlatformAuthInterrupts().resolve_interrupt(svc)
        if ok and state in {'owner_grade', 'partial', 'blocked'}:
            return {
                'status': 'completed',
                'output': {
                    'service': svc,
                    'action': act,
                    'state': state or 'unknown',
                    'owner_grade_ok': owner_grade_ok,
                    'registry': registry_after or registry_before,
                },
                'agent': 'platform_readiness',
            }
        return {
            'status': 'failed',
            'error': detail or f'owner_grade_validate_failed:{svc}',
            'output': {'service': svc, 'action': act, 'state': state or 'unknown'},
            'agent': 'platform_readiness',
        }

    return {'status': 'failed', 'error': f'unsupported_platform_readiness_action:{act}', 'agent': 'platform_readiness'}
