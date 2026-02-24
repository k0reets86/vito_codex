import re
import urllib.request
from typing import Dict


def _strip_html(text: str) -> str:
    # Remove scripts/styles
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    # Drop tags
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_url(url: str, timeout: int = 10, max_bytes: int = 200_000) -> Dict[str, str]:
    """Fetch a URL without LLM and return basic extracted info."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) VITO/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(max_bytes)
        encoding = resp.headers.get_content_charset() or "utf-8"
    html = raw.decode(encoding, errors="ignore")
    # Title
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = m.group(1).strip() if m else ""
    text = _strip_html(html)
    return {
        "title": title,
        "text": text[:1500],
    }
