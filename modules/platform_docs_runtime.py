from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT

KNOWLEDGE_MD = PROJECT_ROOT / 'docs' / 'platform_knowledge.md'
RULES_UPDATES_MD = PROJECT_ROOT / 'docs' / 'platform_rules_updates.md'
CACHE_PATH = PROJECT_ROOT / 'runtime' / 'platform_docs_runtime.json'
SCHEMA_VERSION = 2

ALIASES = {
    'amazon': 'amazon_kdp',
    'kdp': 'amazon_kdp',
    'x': 'twitter',
    'ko-fi': 'kofi',
}
SERVICE_PATTERNS = {
    'amazon_kdp': [r'\bamazon kdp\b', r'\bkdp\b', r'\bpaperback\b', r'\bhardcover\b', r'\bebook\b'],
    'etsy': [r'\betsy\b'],
    'gumroad': [r'\bgumroad\b'],
    'kofi': [r'\bko-fi\b', r'\bkofi\b'],
    'printful': [r'\bprintful\b'],
    'reddit': [r'\breddit\b'],
    'pinterest': [r'\bpinterest\b'],
    'twitter': [r'\btwitter\b', r'\bx\b', r'\bx developer platform\b'],
    'instagram': [r'\binstagram\b'],
    'threads': [r'\bthreads\b'],
    'shopify': [r'\bshopify\b'],
    'payhip': [r'\bpayhip\b'],
    'lemon_squeezy': [r'\blemon squeezy\b', r'\blemonsqueezy\b'],
    'youtube': [r'\byoutube\b'],
    'linkedin': [r'\blinkedin\b'],
    'discord': [r'\bdiscord\b'],
    'tiktok': [r'\btiktok\b'],
    'woocommerce': [r'\bwoocommerce\b'],
    'wordpress': [r'\bwordpress\b'],
    'medium': [r'\bmedium\b'],
}


def _alias(service: str) -> str:
    low = str(service or '').strip().lower()
    return ALIASES.get(low, low)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return ''


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = ''
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith('## '):
            if current_title:
                sections.append((current_title, '\n'.join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title:
        sections.append((current_title, '\n'.join(current_lines).strip()))
    return sections


def _matches(service: str, title: str, body: str) -> bool:
    hay = f'{title}\n{body}'.lower()
    pats = SERVICE_PATTERNS.get(service, [rf'\b{re.escape(service)}\b'])
    return any(re.search(p, hay, re.I) for p in pats)


def _extract_bullets(text: str, limit: int = 20) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('- '):
            out.append(s[2:].strip())
        elif s.startswith('* '):
            out.append(s[2:].strip())
    seen: set[str] = set()
    dedup: list[str] = []
    for item in out:
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= limit:
            break
    return dedup


def _extract_labeled_list(body: str, label: str, limit: int = 20) -> list[str]:
    lines = body.splitlines()
    out: list[str] = []
    active = False
    for line in lines:
        stripped = line.strip()
        if re.fullmatch(re.escape(label) + r':?', stripped, re.I):
            active = True
            continue
        if active and stripped.startswith('## '):
            break
        if active and stripped and not stripped.startswith('- '):
            if out:
                break
            continue
        if active and stripped.startswith('- '):
            out.append(stripped[2:].strip())
            if len(out) >= limit:
                break
    return out


def build_docs_runtime(services: list[str] | None = None) -> dict[str, Any]:
    wanted = {_alias(s) for s in (services or []) if str(s).strip()}
    knowledge_text = _read(KNOWLEDGE_MD)
    rules_text = _read(RULES_UPDATES_MD)
    knowledge_sections = _split_sections(knowledge_text)
    rules_sections = _split_sections(rules_text)
    services_out: dict[str, Any] = {}
    all_services = wanted or set(SERVICE_PATTERNS.keys())
    for svc in sorted(all_services):
        matched_knowledge = [(t, b) for t, b in knowledge_sections if _matches(svc, t, b)]
        matched_rules = [(t, b) for t, b in rules_sections if _matches(svc, t, b)]
        policy_notes: list[str] = []
        lessons: list[str] = []
        anti_patterns: list[str] = []
        evidence_fragments: list[str] = []
        for title, body in matched_knowledge:
            policy_notes.extend(_extract_bullets(body, limit=50))
            lessons.extend(_extract_labeled_list(body, 'Lessons', limit=20))
            anti_patterns.extend(_extract_labeled_list(body, 'Anti-patterns', limit=20))
            m = re.search(r'^Evidence:\s*(.+)$', body, re.M)
            if m:
                evidence_fragments.append(m.group(1)[:400])
        rules_updates = []
        for title, body in matched_rules[:10]:
            bullets = [ln.strip()[2:].strip() for ln in body.splitlines() if ln.strip().startswith('- ')]
            rules_updates.append({
                'title': title,
                'excerpt': ' '.join(bullets[:3])[:400] if bullets else body[:400].replace('\n', ' '),
            })
        services_out[svc] = {
            'service': svc,
            'knowledge_sections': [t for t, _ in matched_knowledge[:30]],
            'rules_sections': [t for t, _ in matched_rules[:30]],
            'policy_notes': _extract_bullets('\n'.join(policy_notes), limit=50) if policy_notes else [],
            'lessons': _extract_bullets('\n'.join(f'- {x}' for x in lessons), limit=50) if lessons else [],
            'anti_patterns': _extract_bullets('\n'.join(f'- {x}' for x in anti_patterns), limit=50) if anti_patterns else [],
            'rules_updates': rules_updates,
            'evidence_fragments': evidence_fragments[:10],
            'knowledge_count': len(matched_knowledge),
            'rules_count': len(matched_rules),
        }
    return {
        'services': services_out,
        'schema_version': SCHEMA_VERSION,
        'source_meta': {
            'knowledge_md': str(KNOWLEDGE_MD),
            'rules_updates_md': str(RULES_UPDATES_MD),
            'knowledge_hash': _hash_text(knowledge_text),
            'rules_hash': _hash_text(rules_text),
        },
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }


def sync_docs_runtime(services: list[str] | None = None) -> dict[str, Any]:
    data = build_docs_runtime(services)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def get_docs_runtime(service: str, *, refresh: bool = False) -> dict[str, Any]:
    svc = _alias(service)
    if refresh or not CACHE_PATH.exists():
        data = sync_docs_runtime([svc])
        return dict((data.get('services') or {}).get(svc) or {})
    try:
        data = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except Exception:
        data = sync_docs_runtime([svc])
    if not isinstance(data, dict) or int(data.get('schema_version') or 0) < SCHEMA_VERSION:
        data = sync_docs_runtime([svc])
    services = data.get('services') if isinstance(data, dict) else {}
    entry = services.get(svc) if isinstance(services, dict) else None
    if not isinstance(entry, dict):
        data = sync_docs_runtime([svc])
        entry = (data.get('services') or {}).get(svc) or {}
    return dict(entry or {})
