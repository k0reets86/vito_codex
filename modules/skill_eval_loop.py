"""Skill eval loop with grader/comparator/analyzer (blind-friendly)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvalCase:
    id: str
    prompt: str
    should_trigger: bool
    required_terms: list[str]
    forbidden_terms: list[str]


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]{2,}", str(text or "").lower())}


def _trigger_score(description: str, prompt: str) -> float:
    d = _tokenize(description)
    p = _tokenize(prompt)
    if not d or not p:
        return 0.0
    inter = len(d & p)
    return float(inter) / float(max(1, len(p)))


def _trigger_predict(description: str, prompt: str, threshold: float = 0.12) -> bool:
    return _trigger_score(description, prompt) >= max(0.01, float(threshold))


def _grade_case(description: str, case: EvalCase) -> dict[str, Any]:
    predicted = _trigger_predict(description, case.prompt)
    score = _trigger_score(description, case.prompt)
    required_ok = all(str(t or "").lower() in str(description or "").lower() for t in (case.required_terms or []))
    forbidden_hit = any(str(t or "").lower() in str(description or "").lower() for t in (case.forbidden_terms or []))
    pass_pred = predicted == bool(case.should_trigger)
    passed = bool(pass_pred and required_ok and not forbidden_hit)
    return {
        "id": case.id,
        "prompt": case.prompt,
        "should_trigger": bool(case.should_trigger),
        "predicted_trigger": bool(predicted),
        "trigger_score": round(score, 4),
        "required_ok": bool(required_ok),
        "forbidden_hit": bool(forbidden_hit),
        "passed": bool(passed),
    }


def _blind_compare(grade_a: dict[str, Any], grade_b: dict[str, Any]) -> str:
    # Deterministic blind comparator: chooses output with better pass/safety score.
    sa = float(grade_a.get("passed", False)) * 2.0 + float(grade_a.get("required_ok", False)) - float(grade_a.get("forbidden_hit", False))
    sb = float(grade_b.get("passed", False)) * 2.0 + float(grade_b.get("required_ok", False)) - float(grade_b.get("forbidden_hit", False))
    if sa > sb:
        return "A"
    if sb > sa:
        return "B"
    # Tie-break by higher trigger score closeness to expectation.
    ta = float(grade_a.get("trigger_score", 0.0))
    tb = float(grade_b.get("trigger_score", 0.0))
    return "A" if ta >= tb else "B"


def _analyze_failures(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [r for r in case_rows if not bool(r.get("passed"))]
    reasons: dict[str, int] = {"prediction": 0, "required_terms": 0, "forbidden_terms": 0}
    for row in failed:
        if bool(row.get("predicted_trigger")) != bool(row.get("should_trigger")):
            reasons["prediction"] += 1
        if not bool(row.get("required_ok")):
            reasons["required_terms"] += 1
        if bool(row.get("forbidden_hit")):
            reasons["forbidden_terms"] += 1
    top_reason = max(reasons, key=lambda k: reasons[k]) if failed else "none"
    return {"failed": len(failed), "reasons": reasons, "top_reason": top_reason}


def _suggest_description_patch(description: str, analysis: dict[str, Any], eval_cases: list[EvalCase]) -> str:
    desc = str(description or "").strip()
    if not desc:
        desc = "Используй этот навык для профильных запросов."
    top = str((analysis or {}).get("top_reason") or "")
    if top == "prediction":
        positives = [c for c in eval_cases if c.should_trigger]
        hints = []
        for c in positives[:4]:
            for tok in _tokenize(c.prompt):
                if tok not in _tokenize(desc):
                    hints.append(tok)
                if len(hints) >= 8:
                    break
            if len(hints) >= 8:
                break
        if hints:
            desc += "\nТриггеры: " + ", ".join(sorted(set(hints)))
    elif top == "required_terms":
        missing = []
        for c in eval_cases:
            for t in c.required_terms:
                if str(t).strip() and str(t).lower() not in desc.lower():
                    missing.append(str(t).strip())
        if missing:
            desc += "\nОбязательно покрывать: " + ", ".join(sorted(set(missing))[:12])
    elif top == "forbidden_terms":
        bad = []
        for c in eval_cases:
            bad.extend([t for t in c.forbidden_terms if t])
        if bad:
            desc += "\nНе применять для: " + ", ".join(sorted(set(bad))[:12])
    return desc


def load_eval_suite(path: str | Path) -> list[EvalCase]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data.get("evals") if isinstance(data, dict) else data
    out: list[EvalCase] = []
    for i, row in enumerate(rows or [], start=1):
        if not isinstance(row, dict):
            continue
        out.append(
            EvalCase(
                id=str(row.get("id") or f"case_{i}"),
                prompt=str(row.get("prompt") or "").strip(),
                should_trigger=bool(row.get("should_trigger", True)),
                required_terms=[str(x).strip() for x in (row.get("required_terms") or []) if str(x).strip()],
                forbidden_terms=[str(x).strip() for x in (row.get("forbidden_terms") or []) if str(x).strip()],
            )
        )
    return out


def run_skill_eval_once(
    candidate_description: str,
    baseline_description: str,
    eval_cases: list[EvalCase],
) -> dict[str, Any]:
    candidate_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    wins = {"candidate": 0, "baseline": 0}
    for case in eval_cases:
        c = _grade_case(candidate_description, case)
        b = _grade_case(baseline_description, case)
        winner = _blind_compare(c, b)
        if winner == "A":
            wins["candidate"] += 1
        else:
            wins["baseline"] += 1
        c["blind_bucket"] = "A"
        b["blind_bucket"] = "B"
        c["winner"] = winner
        b["winner"] = winner
        candidate_rows.append(c)
        baseline_rows.append(b)
    cand_pass = sum(1 for r in candidate_rows if r["passed"])
    base_pass = sum(1 for r in baseline_rows if r["passed"])
    total = max(1, len(eval_cases))
    cand_analysis = _analyze_failures(candidate_rows)
    base_analysis = _analyze_failures(baseline_rows)
    return {
        "candidate": {
            "pass_rate": round(cand_pass / total, 4),
            "passed": cand_pass,
            "total": total,
            "rows": candidate_rows,
            "analysis": cand_analysis,
        },
        "baseline": {
            "pass_rate": round(base_pass / total, 4),
            "passed": base_pass,
            "total": total,
            "rows": baseline_rows,
            "analysis": base_analysis,
        },
        "blind_compare": wins,
    }


def run_skill_eval_loop(
    candidate_description: str,
    baseline_description: str,
    eval_cases: list[EvalCase],
    max_iters: int = 3,
) -> dict[str, Any]:
    cand = str(candidate_description or "")
    base = str(baseline_description or "")
    history: list[dict[str, Any]] = []
    best = run_skill_eval_once(cand, base, eval_cases)
    history.append(best)
    best_rate = float(best["candidate"]["pass_rate"])
    for _ in range(max(0, int(max_iters) - 1)):
        analysis = best["candidate"]["analysis"]
        improved = _suggest_description_patch(cand, analysis, eval_cases)
        if improved.strip() == cand.strip():
            break
        trial = run_skill_eval_once(improved, base, eval_cases)
        history.append(trial)
        trial_rate = float(trial["candidate"]["pass_rate"])
        if trial_rate >= best_rate:
            cand = improved
            best = trial
            best_rate = trial_rate
        else:
            break
    return {
        "best_candidate_description": cand,
        "best_pass_rate": round(best_rate, 4),
        "history": history,
        "iterations": len(history),
    }

