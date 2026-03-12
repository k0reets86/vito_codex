from modules.vito_benchmarks import VITOBenchmarks


def test_vito_benchmarks_structured_scoring():
    bench = VITOBenchmarks(threshold_delta=0.05)
    result = bench.evaluate([
        {'name': 'a', 'score': 0.61, 'evidence': {'tests': 10}},
        {'name': 'b', 'score': 0.72, 'evidence': {'tests': 12}},
    ], baseline_score=0.6)
    assert result['approved'] is True
    assert result['best_score']['name'] == 'b'
    assert len(result['scores']) == 2


def test_vito_benchmarks_respects_scenario_scores():
    bench = VITOBenchmarks(threshold_delta=0.05, scenario_pass_threshold=0.75)
    result = bench.evaluate([
        {
            'name': 'scenario_candidate',
            'score': 0.80,
            'scenario_scores': [{'score': 0.9, 'passed': True}, {'score': 0.4, 'passed': False}],
            'evidence': {'tests': 3},
        }
    ], baseline_score=0.6)
    assert result['approved'] is False
    summary = result['scores'][0]['evidence']['scenario_summary']
    assert summary['count'] == 2
    assert summary['pass_rate'] == 0.5
