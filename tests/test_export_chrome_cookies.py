from scripts.export_chrome_cookies import SERVICE_DOMAINS


def test_export_chrome_cookies_has_required_services():
    required = {
        "amazon_kdp",
        "etsy",
        "gumroad",
        "kofi",
        "printful",
        "twitter",
        "reddit",
        "threads",
        "instagram",
        "facebook",
        "pinterest",
        "youtube",
        "linkedin",
        "tiktok",
    }
    assert required.issubset(set(SERVICE_DOMAINS.keys()))

