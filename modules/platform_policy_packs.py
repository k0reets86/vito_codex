from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT

KNOWLEDGE_MD = PROJECT_ROOT / 'docs' / 'platform_knowledge.md'
RULES_UPDATES_MD = PROJECT_ROOT / 'docs' / 'platform_rules_updates.md'

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
    'twitter': [r'\btwitter\b', r'\bx\b developer platform', r'\bx developer platform\b'],
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
    dedup: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= limit:
            break
    return dedup


def _extract_updates(service: str, text: str, limit: int = 10) -> list[dict[str, str]]:
    chunks = re.split(r'(?m)^## ', text)
    out: list[dict[str, str]] = []
    for raw in chunks[1:]:
        title, _, body = raw.partition('\n\n')
        full = f'{title}\n{body}'
        if _matches(service, title, body):
            lines = [ln.strip('- ').strip() for ln in body.splitlines() if ln.strip().startswith('- ')]
            excerpt = ' '.join(lines[:3])[:400] if lines else body[:400].replace('\n', ' ')
            out.append({'title': title.strip(), 'excerpt': excerpt})
            if len(out) >= limit:
                break
    return out


def build_service_policy_pack(service: str) -> dict[str, Any]:
    svc = _alias(service)
    knowledge = _read(KNOWLEDGE_MD)
    sections = _split_sections(knowledge)
    matched = [(t, b) for t, b in sections if _matches(svc, t, b)]
    policy_notes: list[str] = []
    section_titles: list[str] = []
    for title, body in matched:
        section_titles.append(title)
        policy_notes.extend(_extract_bullets(body, limit=50))
    dedup_notes: list[str] = []
    seen: set[str] = set()
    for note in policy_notes:
        k = note.lower()
        if not note or k in seen:
            continue
        seen.add(k)
        dedup_notes.append(note)
    updates = _extract_updates(svc, _read(RULES_UPDATES_MD), limit=10)
    return {
        'service': svc,
        'policy_section_titles': section_titles[:20],
        'policy_notes': dedup_notes[:30],
        'rules_updates': updates,
        'has_policy_knowledge': bool(matched),
        'has_rules_updates': bool(updates),
    }
