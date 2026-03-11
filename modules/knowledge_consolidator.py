from __future__ import annotations

from typing import Any

from modules.platform_knowledge import search_entries as search_platform_knowledge
from modules.platform_runtime_registry import get_runtime_entry
from modules.platform_readiness import assess_platform_readiness
from modules.owner_policy_packs import build_owner_policy_pack


class KnowledgeConsolidator:
    """Builds one runtime knowledge pack from heterogeneous knowledge sources."""

    def __init__(self, *, memory_manager, reflector=None, evolution_archive=None):
        self.memory_manager = memory_manager
        self.reflector = reflector
        self.evolution_archive = evolution_archive

    def consolidate(
        self,
        *,
        query: str,
        services: list[str] | None = None,
        task_root_id: str = "",
        limit: int = 5,
    ) -> dict[str, Any]:
        query_text = str(query or "").strip()
        svc_list = [str(x).strip().lower() for x in (services or []) if str(x).strip()]
        knowledge_hits = list(self.memory_manager.search_knowledge(query_text, n_results=max(1, int(limit or 5))) or [])
        reflection_hits = self._reflection_hits(query_text, limit=max(2, int(limit or 5)))
        platform_hits = self._platform_hits(query_text, svc_list, limit=max(2, int(limit or 5)))
        archive_hits = self._archive_hits(task_root_id=task_root_id, limit=max(2, int(limit or 5)))
        graph_neighbors = self._graph_neighbors(knowledge_hits, task_root_id=task_root_id, limit=max(2, int(limit or 5)))

        readiness = self._readiness_hits(svc_list)
        proof_contract = self._proof_contract(platform_hits)
        blockers = self._blockers(readiness, platform_hits)
        next_actions = self._next_actions(readiness, platform_hits)
        confidence = self._confidence(
            semantic_hits=len(knowledge_hits),
            reflection_hits=len(reflection_hits),
            platform_hits=len(platform_hits),
            archive_hits=len(archive_hits),
            graph_hits=len(graph_neighbors),
            services=svc_list,
            blockers=blockers,
        )
        signals = {
            "semantic_knowledge": len(knowledge_hits),
            "reflections": len(reflection_hits),
            "platform_knowledge": len(platform_hits),
            "evolution_archive": len(archive_hits),
            "knowledge_graph": len(graph_neighbors),
            "readiness": len(readiness),
            "blockers": len(blockers),
        }
        owner_policy = build_owner_policy_pack(refresh=False)
        signals['owner_policy_rules'] = int(owner_policy.get('active_rule_count') or 0)
        summary = self._summary(query_text, services=svc_list, signals=signals)

        return {
            "query": query_text,
            "services": svc_list,
            "task_root_id": str(task_root_id or ""),
            "summary": summary,
            "signals": signals,
            "confidence": confidence,
            "blockers": blockers,
            "next_actions": next_actions,
            "proof_contract": proof_contract,
            "readiness": readiness,
            "knowledge_hits": knowledge_hits,
            "reflection_hits": reflection_hits,
            "platform_hits": platform_hits,
            "archive_hits": archive_hits,
            "graph_neighbors": graph_neighbors,
            "owner_policy": owner_policy,
        }

    def _reflection_hits(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        if not self.reflector:
            return []
        try:
            return list(self.reflector.top_relevant(query, n=max(1, limit)) or [])
        except Exception:
            return []

    def _readiness_hits(self, services: list[str]) -> list[dict[str, Any]]:
        if not services:
            return []
        try:
            rows = assess_platform_readiness(services)
            return [dict(x) for x in (rows or []) if isinstance(x, dict)]
        except Exception:
            return []

    @staticmethod
    def _proof_contract(platform_hits: list[dict[str, Any]]) -> dict[str, Any]:
        required_artifacts: list[str] = []
        verify_points: list[str] = []
        services: list[str] = []
        for hit in platform_hits or []:
            entry = hit.get('runtime_entry') if isinstance(hit, dict) else {}
            if not isinstance(entry, dict):
                continue
            services.append(str(hit.get('service') or entry.get('service') or ''))
            required_artifacts.extend([str(x) for x in (entry.get('required_artifacts') or [])])
            verify_points.extend([str(x) for x in (entry.get('verify_points') or [])])
        def _dedupe(vals: list[str]) -> list[str]:
            out=[]; seen=set()
            for v in vals:
                k=str(v or '').strip().lower()
                if not k or k in seen:
                    continue
                seen.add(k); out.append(str(v).strip())
            return out
        return {
            'services': _dedupe(services),
            'required_artifacts': _dedupe(required_artifacts)[:30],
            'verify_points': _dedupe(verify_points)[:30],
        }

    @staticmethod
    def _blockers(readiness: list[dict[str, Any]], platform_hits: list[dict[str, Any]]) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in readiness or []:
            service = str(row.get('service') or '').strip().lower()
            blocker = str(row.get('blocker') or '').strip().lower()
            if service and blocker and (service, blocker) not in seen:
                seen.add((service, blocker))
                blockers.append({'service': service, 'blocker': blocker})
        for hit in platform_hits or []:
            service = str(hit.get('service') or '').strip().lower()
            entry = hit.get('runtime_entry') if isinstance(hit, dict) else {}
            for note in list((entry or {}).get('avoid_patterns') or [])[:10]:
                low = str(note or '').strip().lower()
                if any(token in low for token in ('do not', 'avoid', 'blocked', 'ban', 'captcha', 'missing')):
                    key = (service, low[:120])
                    if service and key not in seen:
                        seen.add(key)
                        blockers.append({'service': service, 'blocker': str(note).strip()[:160]})
        return blockers[:20]

    @staticmethod
    def _next_actions(readiness: list[dict[str, Any]], platform_hits: list[dict[str, Any]]) -> list[str]:
        actions: list[str] = []
        seen: set[str] = set()
        for row in readiness or []:
            action = str(row.get('recommended_action') or '').strip()
            if action and action not in seen:
                seen.add(action)
                actions.append(action)
        for hit in platform_hits or []:
            entry = hit.get('runtime_entry') if isinstance(hit, dict) else {}
            for action in list((entry or {}).get('recommended_steps') or [])[:8]:
                a = str(action or '').strip()
                if a and a not in seen:
                    seen.add(a)
                    actions.append(a)
        return actions[:20]

    @staticmethod
    def _confidence(*, semantic_hits: int, reflection_hits: int, platform_hits: int, archive_hits: int, graph_hits: int, services: list[str], blockers: list[dict[str, str]]) -> float:
        score = 0.0
        score += min(0.35, semantic_hits * 0.08)
        score += min(0.15, reflection_hits * 0.05)
        score += min(0.20, platform_hits * 0.08)
        score += min(0.10, archive_hits * 0.04)
        score += min(0.10, graph_hits * 0.03)
        if services:
            score += min(0.10, len(services) * 0.03)
        score -= min(0.25, len(blockers) * 0.06)
        return round(max(0.0, min(1.0, score)), 4)

    def _platform_hits(self, query: str, services: list[str], *, limit: int) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        for service in services:
            try:
                entry = get_runtime_entry(service)
            except Exception:
                entry = {}
            key = str(entry.get("service") or service or "")
            if key and key not in seen:
                seen.add(key)
                hits.append(
                    {
                        "service": key,
                        "content": " ".join(
                            list(entry.get("policy_notes") or [])[:8]
                            + list(entry.get("recommended_steps") or [])[:8]
                            + list(entry.get("avoid_patterns") or [])[:6]
                        )[:4000],
                        "runtime_entry": entry,
                    }
                )
        try:
            rows = search_platform_knowledge(query, limit=limit)
        except Exception:
            rows = []
        for row in rows:
            key = str(row.get("service") or "")
            if key in seen:
                continue
            seen.add(key)
            try:
                row["runtime_entry"] = get_runtime_entry(key)
            except Exception:
                row["runtime_entry"] = {}
            hits.append(row)
        return hits[:limit]

    def _archive_hits(self, *, task_root_id: str, limit: int) -> list[dict[str, Any]]:
        if not self.evolution_archive:
            return []
        try:
            rows = list(self.evolution_archive.recent(limit=max(limit * 3, 10)) or [])
        except Exception:
            return []
        if task_root_id:
            scoped = [row for row in rows if str(row.get("task_root_id") or "") == str(task_root_id)]
            if scoped:
                rows = scoped
        return rows[:limit]

    def _graph_neighbors(
        self,
        knowledge_hits: list[dict[str, Any]],
        *,
        task_root_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        graph = getattr(self.memory_manager, "_knowledge_graph", None)
        if not graph:
            return []
        node_ids: list[str] = []
        if task_root_id:
            node_ids.append(f"goal:{task_root_id}")
        for hit in knowledge_hits[: max(1, limit)]:
            doc_id = str(hit.get("id") or "").strip()
            if doc_id:
                node_ids.append(doc_id)
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for node_id in node_ids:
            try:
                rows = graph.neighbors(node_id, limit=limit)
            except Exception:
                continue
            for row in rows:
                key = (str(row.get("src_id") or ""), str(row.get("relation") or ""), str(row.get("dst_id") or ""))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(row)
        return merged[:limit]

    @staticmethod
    def _summary(query: str, *, services: list[str], signals: dict[str, int]) -> str:
        active_services = ", ".join(services[:4]) if services else "general"
        parts = [
            f"query={query[:120]}",
            f"services={active_services}",
            f"semantic={signals.get('semantic_knowledge', 0)}",
            f"reflections={signals.get('reflections', 0)}",
            f"platform={signals.get('platform_knowledge', 0)}",
            f"archive={signals.get('evolution_archive', 0)}",
            f"graph={signals.get('knowledge_graph', 0)}",
        ]
        return "knowledge_pack " + " ".join(parts)
