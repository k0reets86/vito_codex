from __future__ import annotations

from typing import Any


def score_curriculum(payload: dict[str, Any]) -> dict[str, Any]:
    goals = list((payload or {}).get("goals") or [])
    state = dict((payload or {}).get("state") or {})
    runtime_profile = dict((payload or {}).get("runtime_profile") or {})
    used_skills = list((payload or {}).get("used_skills") or [])
    structure = 1.0 if goals else 0.0
    evidence = 1.0 if state else 0.0
    runtime = 1.0 if runtime_profile else 0.0
    skills = min(1.0, len(used_skills) / 2.0)
    score = round((structure + evidence + runtime + skills) / 4.0 * 10.0, 2)
    return {"agent": "curriculum_agent", "score": score, "goal_count": len(goals), "used_skills": used_skills}


def score_opportunity(payload: dict[str, Any]) -> dict[str, Any]:
    proposals = list((payload or {}).get("proposals") or [])
    runtime_profile = dict((payload or {}).get("runtime_profile") or {})
    used_skills = list((payload or {}).get("used_skills") or [])
    top = dict(proposals[0]) if proposals else {}
    structure = 1.0 if proposals else 0.0
    monetization = 1.0 if top.get("expected_revenue") is not None else 0.0
    runtime = 1.0 if runtime_profile else 0.0
    skills = min(1.0, len(used_skills) / 2.0)
    score = round((structure + monetization + runtime + skills) / 4.0 * 10.0, 2)
    return {"agent": "opportunity_scout", "score": score, "proposal_count": len(proposals), "used_skills": used_skills}


def score_self_evolver(payload: dict[str, Any]) -> dict[str, Any]:
    proposals = list((payload or {}).get("proposals") or [])
    runtime_profile = dict((payload or {}).get("runtime_profile") or {})
    archive_ref = bool((payload or {}).get("archive_ref"))
    used_skills = list((payload or {}).get("used_skills") or [])
    structure = 1.0 if proposals else 0.0
    scoring = 1.0 if proposals and proposals[0].get("proposal_score") is not None else 0.0
    runtime = 1.0 if runtime_profile else 0.0
    archival = 1.0 if archive_ref else 0.0
    skills = min(1.0, len(used_skills) / 2.0)
    score = round((structure + scoring + runtime + archival + skills) / 5.0 * 10.0, 2)
    return {"agent": "self_evolver", "score": score, "proposal_count": len(proposals), "used_skills": used_skills}


def run_autonomy_matrix(*, curriculum: dict[str, Any], opportunity: dict[str, Any], self_evolver: dict[str, Any]) -> dict[str, Any]:
    results = [
        score_curriculum(curriculum),
        score_opportunity(opportunity),
        score_self_evolver(self_evolver),
    ]
    avg = round(sum(float(r["score"]) for r in results) / max(1, len(results)), 2)
    return {"results": results, "average_score": avg, "all_agents_scored": all(r["score"] >= 0 for r in results)}
