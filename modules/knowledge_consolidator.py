from __future__ import annotations

from typing import Any

from modules.platform_knowledge import search_entries as search_platform_knowledge


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

        signals = {
            "semantic_knowledge": len(knowledge_hits),
            "reflections": len(reflection_hits),
            "platform_knowledge": len(platform_hits),
            "evolution_archive": len(archive_hits),
            "knowledge_graph": len(graph_neighbors),
        }
        summary = self._summary(query_text, services=svc_list, signals=signals)

        return {
            "query": query_text,
            "services": svc_list,
            "task_root_id": str(task_root_id or ""),
            "summary": summary,
            "signals": signals,
            "knowledge_hits": knowledge_hits,
            "reflection_hits": reflection_hits,
            "platform_hits": platform_hits,
            "archive_hits": archive_hits,
            "graph_neighbors": graph_neighbors,
        }

    def _reflection_hits(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        if not self.reflector:
            return []
        try:
            return list(self.reflector.top_relevant(query, n=max(1, limit)) or [])
        except Exception:
            return []

    def _platform_hits(self, query: str, services: list[str], *, limit: int) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        for service in services:
            try:
                rows = search_platform_knowledge(service, limit=limit)
            except Exception:
                rows = []
            for row in rows:
                key = str(row.get("service") or "")
                if key in seen:
                    continue
                seen.add(key)
                hits.append(row)
        try:
            rows = search_platform_knowledge(query, limit=limit)
        except Exception:
            rows = []
        for row in rows:
            key = str(row.get("service") or "")
            if key in seen:
                continue
            seen.add(key)
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
