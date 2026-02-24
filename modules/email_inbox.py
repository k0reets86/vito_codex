"""Email inbox helper for verification codes (IMAP/Gmail).

Fetches latest verification code or link from inbox without LLM.
"""

import imaplib
import email
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


def _extract_code(text: str) -> Optional[str]:
    # Common patterns: 4-8 digit codes
    m = re.search(r"\b(\d{4,8})\b", text)
    return m.group(1) if m else None


def _extract_link(text: str) -> Optional[str]:
    m = re.search(r"https?://[^\s)>\"]+", text)
    return m.group(0) if m else None


def fetch_latest_code(
    address: str,
    password: str,
    since_minutes: int = 15,
    from_filter: str = "",
    subject_filter: str = "",
    prefer_link: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (code_or_link, snippet) from latest email matching filters.

    Uses IMAP. For Gmail, app password is recommended.
    """
    if not address or not password:
        return None, None

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(address, password)
    imap.select("INBOX")

    since_date = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime("%d-%b-%Y")
    criteria = [f'SINCE "{since_date}"']
    if from_filter:
        criteria.append(f'FROM "{from_filter}"')
    if subject_filter:
        criteria.append(f'SUBJECT "{subject_filter}"')
    query = " ".join(criteria)
    typ, data = imap.search(None, query)
    if typ != "OK":
        imap.logout()
        return None, None

    ids = data[0].split()
    ids = ids[-10:]  # last 10
    ids = list(reversed(ids))  # newest first
    for msg_id in ids:
        typ, msg_data = imap.fetch(msg_id, "(RFC822)")
        if typ != "OK":
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        parts = []
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ("text/plain", "text/html"):
                    try:
                        parts.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore"))
                    except Exception:
                        pass
        else:
            try:
                parts.append(msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore"))
            except Exception:
                pass
        body = "\n".join(p for p in parts if p)
        snippet = body[:500] if body else ""
        if prefer_link:
            link = _extract_link(body)
            if link:
                imap.logout()
                return link, snippet
        code = _extract_code(body)
        if code:
            imap.logout()
            return code, snippet

    imap.logout()
    return None, None


def wait_for_code(
    address: str,
    password: str,
    from_filter: str = "",
    subject_filter: str = "",
    prefer_link: bool = False,
    timeout_sec: int = 120,
    poll_sec: int = 5,
) -> Tuple[Optional[str], Optional[str]]:
    """Poll inbox until code arrives or timeout."""
    start = time.time()
    while time.time() - start < timeout_sec:
        code, snippet = fetch_latest_code(
            address=address,
            password=password,
            since_minutes=30,
            from_filter=from_filter,
            subject_filter=subject_filter,
            prefer_link=prefer_link,
        )
        if code:
            return code, snippet
        time.sleep(poll_sec)
    return None, None

