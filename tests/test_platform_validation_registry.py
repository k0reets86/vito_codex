from modules.platform_validation_registry import (
    load_platform_validation_registry,
    record_platform_validation_result,
)


def test_record_platform_validation_result_persists_state():
    record_platform_validation_result(
        {
            'platform': 'etsy',
            'state': 'partial',
            'owner_grade_ok': False,
            'blocker': 'missing_session',
            'mode': 'editor_probe',
        }
    )
    data = load_platform_validation_registry()
    assert data['etsy']['state'] == 'partial'
    assert data['etsy']['blocker'] == 'missing_session'
