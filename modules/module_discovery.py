
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ModuleCandidate:
    source: str
    name: str
    summary: str
    url: str
    score: float
    tags: list[str]


class ModuleDiscovery:
    """Discover candidate modules from PyPI/GitHub and rank them lightly."""

    def __init__(self, user_agent: str = 'vito-module-discovery/1.0'):
        self.user_agent = user_agent

    def discover_pypi(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = urllib.parse.quote_plus(query.strip())
        url = f'https://pypi.org/search/?q={q}'
        req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode(errors='replace')
        items: list[dict[str, Any]] = []
        import re
        pattern = re.compile(r'<a class="package-snippet" href="([^"]+)">.*?<span class="package-snippet__name">([^<]+)</span>.*?<p class="package-snippet__description">([^<]*)</p>', re.S)
        for href, name, summary in pattern.findall(html)[:max(1, int(limit or 5))]:
            items.append(asdict(ModuleCandidate('pypi', name.strip(), summary.strip(), f'https://pypi.org{href}', self._score(name, summary, query), self._tags(name, summary))))
        return items

    def discover_github(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = urllib.parse.quote_plus(query.strip())
        url = f'https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={max(1, int(limit or 5))}'
        req = urllib.request.Request(url, headers={'User-Agent': self.user_agent, 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode(errors='replace'))
        items: list[dict[str, Any]] = []
        for row in list(data.get('items') or [])[:max(1, int(limit or 5))]:
            name = str(row.get('full_name') or row.get('name') or '')
            summary = str(row.get('description') or '')
            items.append(asdict(ModuleCandidate('github', name, summary, str(row.get('html_url') or ''), self._score(name, summary, query), self._tags(name, summary))))
        return items

    def discover(self, query: str, limit: int = 5) -> dict[str, Any]:
        pypi = self.discover_pypi(query, limit=limit)
        github = self.discover_github(query, limit=limit)
        all_items = sorted(pypi + github, key=lambda x: float(x.get('score', 0.0)), reverse=True)
        return {'query': query, 'items': all_items[:max(1, int(limit or 5))]}

    def _score(self, name: str, summary: str, query: str) -> float:
        hay = f'{name} {summary}'.lower()
        terms = [x for x in query.lower().split() if x]
        hits = sum(1 for t in terms if t in hay)
        return min(1.0, 0.3 + hits * 0.2)

    def _tags(self, name: str, summary: str) -> list[str]:
        hay = f'{name} {summary}'.lower()
        tags = []
        for token in ['browser', 'memory', 'agent', 'workflow', 'sandbox', 'benchmark', 'telegram']:
            if token in hay:
                tags.append(token)
        return tags
