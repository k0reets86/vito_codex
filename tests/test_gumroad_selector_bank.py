from platforms.gumroad_selector_bank import NEXT_SELECTORS, PUBLISH_SELECTORS, SAVE_SELECTORS


def test_gumroad_selector_bank_non_empty():
    assert len(NEXT_SELECTORS) > 0
    assert len(SAVE_SELECTORS) > 0
    assert len(PUBLISH_SELECTORS) > 0

