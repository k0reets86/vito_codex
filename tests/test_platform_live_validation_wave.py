from pathlib import Path


def test_platform_live_validation_wave_has_expected_platforms():
    script = Path("scripts/platform_live_validation_wave.py")
    text = script.read_text(encoding="utf-8")
    for platform in ("gumroad", "kofi", "pinterest", "twitter", "etsy", "amazon_kdp", "printful"):
        assert platform in text
