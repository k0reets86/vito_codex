"""Lightweight workflow graph with validation and simple traversal."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set


@dataclass
class WorkflowNode:
    name: str
    action: Optional[Callable[[dict], dict]] = None


class WorkflowGraph:
    def __init__(self):
        self.nodes: Dict[str, WorkflowNode] = {}
        self.edges: Dict[str, Set[str]] = {}

    def add_node(self, name: str, action: Optional[Callable[[dict], dict]] = None) -> None:
        if name not in self.nodes:
            self.nodes[name] = WorkflowNode(name=name, action=action)
        if name not in self.edges:
            self.edges[name] = set()

    def add_edge(self, src: str, dst: str) -> None:
        if src not in self.nodes:
            self.add_node(src)
        if dst not in self.nodes:
            self.add_node(dst)
        self.edges[src].add(dst)

    def validate(self) -> bool:
        # Ensure all edges reference known nodes
        for src, dsts in self.edges.items():
            if src not in self.nodes:
                return False
            for d in dsts:
                if d not in self.nodes:
                    return False
        return True

    def next_nodes(self, name: str) -> List[str]:
        return sorted(self.edges.get(name, set()))

    def traverse(self, start: str, context: Optional[dict] = None, limit: int = 50) -> List[str]:
        """Simple DFS traversal for deterministic walk (no parallel execution)."""
        if start not in self.nodes:
            return []
        ctx = context or {}
        visited: List[str] = []
        stack = [start]
        while stack and len(visited) < limit:
            node = stack.pop()
            if node in visited:
                continue
            visited.append(node)
            action = self.nodes[node].action
            if action:
                try:
                    action(ctx)
                except Exception:
                    pass
            nxt = list(self.edges.get(node, set()))
            # deterministic order
            for n in sorted(nxt, reverse=True):
                if n not in visited:
                    stack.append(n)
        return visited
