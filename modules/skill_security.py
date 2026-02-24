"""SkillSecurity — lightweight static checks for skills."""

import re
from typing import Tuple


DANGEROUS_PATTERNS = [
    r"rm\s+-rf",
    r"chmod\s+777",
    r"curl\s+.*\|\s*(sh|bash)",
    r"wget\s+.*\|\s*(sh|bash)",
    r"os\.system\(",
    r"subprocess\.Popen\(",
    r"subprocess\.run\(",
    r"eval\(",
    r"exec\(",
]


def scan_text(text: str) -> Tuple[str, str]:
    """Return (status, notes). status: ok|needs_review|blocked."""
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "needs_review", f"Pattern matched: {pat}"
    return "ok", "No dangerous patterns detected"
