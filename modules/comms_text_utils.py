import re
from urllib.parse import urlparse


def extract_topic_from_request(text: str, fallback: str) -> str:
    s = str(text or "").strip()
    if not s:
        return fallback
    s = re.sub(
        r"(?i)\b(создай|сделай|заполни|подготовь|оформи|редактируй|обнови|опубликуй|запусти|черновик|листинг|товар|книгу|пост|пин)\b",
        "",
        s,
    ).strip(" :,-")
    if not s or re.search(r"[А-Яа-яЁё]", s):
        return fallback
    s = re.sub(r"\s+", " ", s)
    return s[:120] or fallback


def extract_otp_code(text: str) -> str:
    s = str(text or "").strip()
    m = re.search(r"\b(\d{6,8})\b", s)
    return m.group(1) if m else ""


def extract_custom_login_target(text: str) -> str:
    s = str(text or "").strip().lower()
    if not s:
        return ""
    m_url = re.search(r"(https?://[^\s<>\"]+)", s)
    if m_url:
        target = m_url.group(1).rstrip(").,;")
        try:
            parsed = urlparse(target)
            host = (parsed.netloc or "").strip().lower()
            if host:
                return host
        except Exception:
            pass
    m_dom = re.search(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(?:/[^\s]*)?\b", s)
    if m_dom:
        domain = m_dom.group(1).strip()
        if domain in {"kdp.amazon.com", "x.com", "reddit.com", "etsy.com", "gumroad.com"}:
            return ""
        return domain
    return ""


def extract_loose_site_target(text: str, site_alias_urls: dict[str, str] | None = None) -> str:
    s = str(text or "").strip().lower()
    if not s:
        return ""
    compact = re.sub(r"\s+", " ", s)
    for alias, host in dict(site_alias_urls or {}).items():
        if alias in compact:
            return host
    if "укрправд" in compact or "укр правд" in compact:
        return "www.pravda.com.ua"
    m = re.search(r"(?:зайди|зайти|открой|войти)\s+(?:на|в)?\s*([^\n\r,;!?]+)$", compact)
    if not m:
        return ""
    tail = m.group(1).strip().strip(".")
    if not tail:
        return ""
    if "amazon" in tail or "амазон" in tail or "kdp" in tail:
        return ""
    tail = tail.replace(" ", "")
    if not tail:
        return ""
    if re.match(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", tail):
        return tail
    if re.match(r"^[a-z0-9-]{3,40}$", tail):
        return f"{tail}.com"
    return ""
