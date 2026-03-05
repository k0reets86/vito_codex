from modules.skill_eval_loop import EvalCase, run_skill_eval_loop, run_skill_eval_once


def test_skill_eval_once_candidate_beats_baseline():
    evals = [
        EvalCase(id="c1", prompt="опубликуй листинг на gumroad", should_trigger=True, required_terms=["gumroad"], forbidden_terms=[]),
        EvalCase(id="c2", prompt="какая погода в берлине", should_trigger=False, required_terms=[], forbidden_terms=["погода"]),
    ]
    candidate = "Навык для gumroad и листинга цифровых товаров."
    baseline = "Общий чат-бот для любых разговоров про погода."
    out = run_skill_eval_once(candidate, baseline, evals)
    assert out["candidate"]["pass_rate"] >= out["baseline"]["pass_rate"]


def test_skill_eval_loop_runs_iterations():
    evals = [
        EvalCase(id="1", prompt="сделай исследование ниши", should_trigger=True, required_terms=["исслед"], forbidden_terms=[]),
        EvalCase(id="2", prompt="поболтай", should_trigger=False, required_terms=[], forbidden_terms=["поболтай"]),
    ]
    out = run_skill_eval_loop(
        candidate_description="Навык для исследования ниши.",
        baseline_description="Обычный помощник для поболтать.",
        eval_cases=evals,
        max_iters=3,
    )
    assert out["iterations"] >= 1
    assert "best_candidate_description" in out

