from modules.comms_text_utils import (
    extract_custom_login_target,
    extract_loose_site_target,
    extract_otp_code,
    extract_topic_from_request,
)


def test_extract_otp_code_finds_code() -> None:
    assert extract_otp_code("код 123456 для амазон") == "123456"


def test_extract_custom_login_target_prefers_host() -> None:
    assert extract_custom_login_target("зайди на https://example.org/login") == "example.org"


def test_extract_loose_site_target_uses_alias_map() -> None:
    aliases = {"укр правда": "www.pravda.com.ua"}
    assert extract_loose_site_target("зайди на укр правда", aliases) == "www.pravda.com.ua"


def test_extract_topic_from_request_strips_platform_verbs() -> None:
    assert extract_topic_from_request("создай листинг Meme Trend Playbook", "fallback") == "Meme Trend Playbook"
