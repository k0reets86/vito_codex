#!/usr/bin/env python3
"""Run skill eval loop from eval suite JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from modules.skill_eval_loop import load_eval_suite, run_skill_eval_loop


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True, help="Path to evals json")
    ap.add_argument("--candidate", required=True, help="Candidate description")
    ap.add_argument("--baseline", required=True, help="Baseline description")
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    suite = load_eval_suite(args.eval)
    out = run_skill_eval_loop(
        candidate_description=args.candidate,
        baseline_description=args.baseline,
        eval_cases=suite,
        max_iters=args.iters,
    )
    payload = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
        print(str(p))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

