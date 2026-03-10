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
