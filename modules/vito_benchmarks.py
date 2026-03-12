
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

    def __init__(self, threshold_delta: float = 0.05, scenario_pass_threshold: float = 0.75):
        self.threshold_delta = float(threshold_delta or 0.05)
        self.scenario_pass_threshold = float(scenario_pass_threshold or 0.75)

    def evaluate(self, candidates: list[dict[str, Any]], baseline_score: float) -> dict[str, Any]:
        scores: list[BenchmarkScore] = []
        for item in candidates:
            score = float(item.get('score', 0.0) or 0.0)
            scenario_summary = self._scenario_summary(item)
            scenario_ok = bool(
                scenario_summary["count"] == 0
                or scenario_summary["pass_rate"] >= self.scenario_pass_threshold
            )
            passed = bool(score >= baseline_score + self.threshold_delta and scenario_ok)
            evidence = dict(item.get('evidence') or {})
            if scenario_summary["count"] > 0:
                evidence = dict(evidence)
                evidence["scenario_summary"] = scenario_summary
            scores.append(BenchmarkScore(
                name=str(item.get('name') or 'candidate'),
                score=score,
                passed=passed,
                evidence=evidence,
            ))
        avg = mean([s.score for s in scores]) if scores else 0.0
        best = max(scores, key=lambda s: s.score, default=BenchmarkScore('none', 0.0, False, {}))
        return {
            'baseline_score': float(baseline_score),
            'threshold_delta': self.threshold_delta,
            'scenario_pass_threshold': self.scenario_pass_threshold,
            'average_score': avg,
            'best_score': asdict(best),
            'scores': [asdict(s) for s in scores],
            'approved': bool(best.passed),
        }

    def _scenario_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        raw = item.get('scenario_scores') or item.get('scenarios') or []
        values: list[float] = []
        passed = 0
        total = 0
        if isinstance(raw, dict):
            raw = list(raw.values())
        for row in list(raw or []):
            total += 1
            if isinstance(row, dict):
                value = float(row.get('score', 0.0) or 0.0)
                is_pass = bool(row.get('passed', value >= 0.7))
            else:
                value = float(row or 0.0)
                is_pass = bool(value >= 0.7)
            values.append(value)
            if is_pass:
                passed += 1
        return {
            "count": total,
            "average_score": mean(values) if values else 0.0,
            "pass_rate": (passed / total) if total else 0.0,
        }
