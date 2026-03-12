
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any
import re


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
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in self._candidate_package_names(query)[: max(1, int(limit or 5)) * 4]:
            if candidate in seen:
                continue
            seen.add(candidate)
            row = self._fetch_pypi_package(candidate, query)
            if row:
                items.append(row)
            if len(items) >= max(1, int(limit or 5)):
                break
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

    def _candidate_package_names(self, query: str) -> list[str]:
        tokens = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if t]
        candidates: list[str] = []
        if tokens:
            candidates.extend([
                "-".join(tokens),
                "_".join(tokens),
                "".join(tokens),
            ])
        for token in tokens:
            candidates.append(token)
        for a, b in zip(tokens, tokens[1:]):
            candidates.extend([f"{a}-{b}", f"{a}_{b}", f"{a}{b}"])
        # Preserve order while deduplicating
        out: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out

    def _fetch_pypi_package(self, name: str, query: str) -> dict[str, Any] | None:
        url = f'https://pypi.org/pypi/{urllib.parse.quote(name)}/json'
        req = urllib.request.Request(url, headers={'User-Agent': self.user_agent, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode(errors='replace'))
        except Exception:
            return None
        info = dict(data.get("info") or {})
        pkg_name = str(info.get("name") or name).strip()
        summary = str(info.get("summary") or "").strip()
        package_url = str(info.get("package_url") or f"https://pypi.org/project/{pkg_name}/")
        return asdict(
            ModuleCandidate(
                'pypi',
                pkg_name,
                summary,
                package_url,
                self._score(pkg_name, summary, query),
                self._tags(pkg_name, summary),
            )
        )
