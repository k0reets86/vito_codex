from vito_tester.scenarios import ALL_TEST_SCENARIOS, STRESS_SCENARIOS, filter_scenarios


def test_all_scenarios_count_matches_spec():
    assert len(ALL_TEST_SCENARIOS) == 61


def test_filter_by_priority_and_category():
    p0 = filter_scenarios(priority="P0")
    assert p0
    assert all(item.priority == "P0" for item in p0)
    seo = filter_scenarios(category="SEO")
    assert len(seo) == 4
    assert all(item.category == "SEO" for item in seo)


def test_stress_scenarios_present():
    ids = {item.scenario_id for item in STRESS_SCENARIOS}
    assert {"RAPID_FIRE", "LONG_TASK", "RECOVERY"} <= ids
