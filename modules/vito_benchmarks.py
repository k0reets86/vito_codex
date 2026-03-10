
from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import mean
from typing import Any


@dataclass
class BenchmarkScore:
    name: str
    score: float
    passed: bool
    evidence: dict[str, Any]


class VITOBenchmarks:
    """Structured benchmark scoring for evolution/apply decisions."""

    def __init__(self, threshold_delta: float = 0.05):
        self.threshold_delta = float(threshold_delta or 0.05)

    def evaluate(self, candidates: list[dict[str, Any]], baseline_score: float) -> dict[str, Any]:
        scores: list[BenchmarkScore] = []
        for item in candidates:
            score = float(item.get('score', 0.0) or 0.0)
            scores.append(BenchmarkScore(
                name=str(item.get('name') or 'candidate'),
                score=score,
                passed=score >= baseline_score + self.threshold_delta,
                evidence=dict(item.get('evidence') or {}),
            ))
        avg = mean([s.score for s in scores]) if scores else 0.0
        best = max(scores, key=lambda s: s.score, default=BenchmarkScore('none', 0.0, False, {}))
        return {
            'baseline_score': float(baseline_score),
            'threshold_delta': self.threshold_delta,
            'average_score': avg,
            'best_score': asdict(best),
            'scores': [asdict(s) for s in scores],
            'approved': bool(best.passed),
        }
