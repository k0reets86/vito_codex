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
from modules.browser_runtime_policy import get_browser_runtime_profile
from modules.platform_auth_interrupts import PlatformAuthInterrupts
from modules.platform_validation_registry import load_platform_validation_registry
from modules.service_session_registry import capture_session_snapshot


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


def _run_platform_probe(service: str) -> tuple[bool, str]:
    svc = str(service or '').strip().lower()
    specific = {
        'etsy': 'scripts/etsy_owner_grade_probe.py',
    }.get(svc)
    if specific and (PROJECT_ROOT / specific).exists():
        return _run_python(specific)
    return _run_python('scripts/platform_live_validation_wave.py')

def _reauth_command_for_service(service: str) -> str:
    svc = str(service or '').strip().lower()
    if svc in {'etsy', 'printful', 'twitter'}:
        return f"python3 scripts/browser_auth_capture.py {svc}"
    if svc == 'amazon_kdp':
        return "python3 scripts/kdp_login_stabilizer.py"
    if svc == 'gumroad':
        return "python3 scripts/gumroad_cookie_capture.py"
    if svc == 'kofi':
        return "python3 scripts/kofi_auth_helper.py browser-capture"
    if svc == 'reddit':
        return "python3 scripts/reddit_auth_helper.py browser-capture"
    if svc == 'pinterest':
        return "python3 scripts/pinterest_auth_helper.py browser-capture"
    return ""



def _attempt_auto_reauth(service: str) -> tuple[bool, str, dict[str, Any]]:
    svc = str(service or '').strip().lower()
    if svc == 'etsy':
        ok, detail = _run_python('scripts/etsy_auth_helper.py auto-login --timeout-sec 120 --storage-path runtime/etsy_storage_state.json')
        payload: dict[str, Any] = {'auto_attempted': True, 'auto_path': 'etsy_auth_helper:auto-login'}
        if ok:
            profile = get_browser_runtime_profile(svc)
            capture_session_snapshot(
                svc,
                storage_state_path=str(profile.get('storage_state_path') or ''),
                profile_dir=str(profile.get('persistent_profile_dir') or ''),
                verified=True,
            )
            payload['auto_reauth_ok'] = True
            return True, detail, payload
        low = str(detail or '').lower()
        payload['auto_reauth_ok'] = False
        if 'otp_required' in low or 'challenge' in low or 'captcha' in low or 'datadome' in low:
            payload['auto_reauth_blocker'] = 'challenge'
            return False, detail, payload
        payload['auto_reauth_blocker'] = 'failed'
        return False, detail, payload
    if svc == 'printful':
        ok, detail = _run_python(
            'scripts/printful_auth_helper.py browser-capture --timeout-sec 120 --storage-path runtime/printful_storage_state.json --headless --auto-submit'
        )
        payload = {'auto_attempted': True, 'auto_path': 'printful_auth_helper:browser-capture'}
        if ok:
            profile = get_browser_runtime_profile(svc)
            capture_session_snapshot(
                svc,
                storage_state_path=str(profile.get('storage_state_path') or ''),
                profile_dir=str(profile.get('persistent_profile_dir') or ''),
                verified=True,
            )
            payload['auto_reauth_ok'] = True
            return True, detail, payload
        payload['auto_reauth_ok'] = False
        payload['auto_reauth_blocker'] = 'failed'
        return False, detail, payload
    return False, '', {'auto_attempted': False}


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
        profile = get_browser_runtime_profile(svc)
        cmd = _reauth_command_for_service(svc)
        auto_ok, auto_detail, auto_payload = _attempt_auto_reauth(svc)
        if auto_ok:
            PlatformAuthInterrupts().resolve_interrupt(svc)
            return {
                'status': 'completed',
                'output': {
                    'service': svc,
                    'action': act,
                    'state': 'session_restored',
                    'reauth_command': cmd,
                    'login_url': str(profile.get('profile_completion_route') or ''),
                    'storage_state_path': str(profile.get('storage_state_path') or ''),
                    'persistent_profile_dir': str(profile.get('persistent_profile_dir') or ''),
                    **auto_payload,
                },
                'agent': 'platform_readiness',
            }
        interrupt_id = PlatformAuthInterrupts().raise_interrupt(svc, block or 'missing_session', detail=auto_detail or act)
        remediation = build_auth_remediation(svc, error=block or 'missing_session', configured=True)
        return {
            'status': 'waiting_approval',
            'error': f'Нужна повторная авторизация для {svc}',
            'output': {
                **remediation,
                'platform_auth_interrupt_id': interrupt_id,
                'reauth_command': cmd,
                'login_url': str(profile.get('profile_completion_route') or ''),
                'storage_state_path': str(profile.get('storage_state_path') or ''),
                'persistent_profile_dir': str(profile.get('persistent_profile_dir') or ''),
                **auto_payload,
                'auto_reauth_detail': auto_detail,
            },
            'agent': 'platform_readiness',
        }

    if act.startswith('run_probe:'):
        ok, detail = _run_platform_probe(svc)
        report = _read_json(_latest_wave_report()) if _latest_wave_report() else {}
        check = _find_service_check(report, svc)
        state = str(check.get('state') or '').strip().lower()
        check_blocker = str(check.get('blocker') or '').strip().lower()
        if check_blocker == 'missing_session':
            PlatformAuthInterrupts().raise_interrupt(svc, 'missing_session', detail=detail or act)
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
        blocker_now = str(registry_after.get('blocker') or registry_before.get('blocker') or '').strip().lower()
        if blocker_now == 'missing_session':
            PlatformAuthInterrupts().raise_interrupt(svc, 'missing_session', detail=detail or act)
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
