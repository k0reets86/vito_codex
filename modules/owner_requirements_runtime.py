from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT

LOG_PATH = PROJECT_ROOT / 'docs' / 'OWNER_REQUIREMENTS_LOG.md'
CACHE_PATH = PROJECT_ROOT / 'runtime' / 'owner_requirements_runtime.json'
SCHEMA_VERSION = 1

RULE_PATTERNS: dict[str, list[str]] = {
    'do_not_reduce_scope': [
        r'не\s+сужать\s+об[ъь]ем',
        r'не\s+сокращать\s+об[ъь]ем',
        r'без\s+самовольного\s+сокращения',
    ],
    'do_not_touch_old_or_published': [
        r'не\s+трогай\s+стар',
        r'не\s+трогай\s+опублик',
        r'старые.*не\s+трога',
        r'published.*not.*auto',
    ],
    'one_object_per_platform': [
        r'один\s+.*об[ъь]ект',
        r'не\s+плодить\s+лишние\s+дубликаты',
        r'one\s+object\s+per\s+platform',
    ],
    'proof_required': [
        r'подтвержд[её]н[а-я]*\s+факт',
        r'подтвержд[её]н[а-я]*\s+на\s+платформ',
        r'скрин',
        r'proof[- ]of[- ]work',
        r'не\s+считать\s+.*заверш',
    ],
    'quiet_execution': [
        r'не\s+спам',
        r'keep\s+comms\s+short',
        r'silent\s+execution',
        r'at\s+most\s+one\s+clarification',
        r'без\s+шум',
    ],
    'continuous_until_done': [
        r'не\s+останавливаться',
        r'continue\s+without\s+stopping',
        r'сразу\s+переходить\s+к\s+следующему\s+пакету',
    ],
    'auth_interrupt_required': [
        r'if\s+missing,\s*request\s+them',
        r'если\s+.*missing.*request',
        r'нужен\s+код',
        r'логин',
        r'otp',
        r'2fa',
    ],
    'browser_first_platform_reality': [
        r'browser-only',
        r'browser-first',
        r'etsy\s+.*browser',
        r'gumroad\s+.*browser',
    ],
}

RULE_REMINDERS: dict[str, str] = {
    'do_not_reduce_scope': 'Не сокращать объем owner-задачи без явного разрешения.',
    'do_not_touch_old_or_published': 'Старые и опубликованные объекты не трогать без явного target/id.',
    'one_object_per_platform': 'На платформе работать только с одним объектом на задачу, без дублей.',
    'proof_required': 'Любой результат подтверждать через reload/screenshot/DOM/state, а не по словам.',
    'quiet_execution': 'Не шуметь владельцу: короткая связь, без лишнего спама.',
    'continuous_until_done': 'Не останавливаться на полпути, если нет внешнего блокера.',
    'auth_interrupt_required': 'Если нужны логин/код/2FA, поднимать явный auth interrupt.',
    'browser_first_platform_reality': 'Для хрупких платформ приоритет browser-first/browser-only path.',
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return ''


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def _extract_bullets(text: str, *, limit: int = 200) -> list[str]:
    out: list[str] = []
    for line in str(text or '').splitlines():
        s = line.strip()
        if s.startswith('- '):
            out.append(s[2:].strip())
        elif s.startswith('* '):
            out.append(s[2:].strip())
        if len(out) >= limit:
            break
    return out


def _match_excerpts(text: str, patterns: list[str], *, limit: int = 5) -> list[str]:
    excerpts: list[str] = []
    lines = [ln.strip() for ln in str(text or '').splitlines() if ln.strip()]
    for line in lines:
        low = line.lower()
        if any(re.search(p, low, re.I) for p in patterns):
            excerpts.append(line[:240])
            if len(excerpts) >= limit:
                break
    return excerpts


def build_owner_requirements_runtime() -> dict[str, Any]:
    text = _read_text(LOG_PATH)
    bullets = _extract_bullets(text, limit=500)
    joined = '\n'.join(bullets) if bullets else text
    rules: list[dict[str, Any]] = []
    flags: dict[str, bool] = {}
    reminders: list[str] = []
    matched_count = 0
    for rule_id, patterns in RULE_PATTERNS.items():
        excerpts = _match_excerpts(joined, patterns, limit=6)
        enabled = bool(excerpts)
        flags[rule_id] = enabled
        if enabled:
            matched_count += 1
            reminders.append(RULE_REMINDERS.get(rule_id, rule_id))
        rules.append({
            'rule_id': rule_id,
            'enabled': enabled,
            'excerpts': excerpts,
            'reminder': RULE_REMINDERS.get(rule_id, rule_id),
            'confidence': 1.0 if enabled else 0.0,
        })
    return {
        'schema_version': SCHEMA_VERSION,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'source_meta': {
            'owner_requirements_log': str(LOG_PATH),
            'owner_requirements_hash': _hash_text(text),
            'bullet_count': len(bullets),
        },
        'flags': flags,
        'rules': rules,
        'reminders': reminders,
        'active_rule_count': matched_count,
    }


def sync_owner_requirements_runtime() -> dict[str, Any]:
    data = build_owner_requirements_runtime()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def get_owner_requirements_runtime(*, refresh: bool = False) -> dict[str, Any]:
    if refresh or not CACHE_PATH.exists():
        return sync_owner_requirements_runtime()
    try:
        data = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return sync_owner_requirements_runtime()
    if not isinstance(data, dict) or int(data.get('schema_version') or 0) < SCHEMA_VERSION:
        return sync_owner_requirements_runtime()
    return data
