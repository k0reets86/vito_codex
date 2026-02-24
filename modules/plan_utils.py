import re


def parse_plan(text: str, max_steps: int = 7) -> list[str]:
    """Parse LLM plan text into a list of steps.

    Handles cases where the model returns a single line with numbered items.
    """
    if not text:
        return []
    raw = text.strip()
    # First split by newlines
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    steps = [re.sub(r"^[0-9]+[\\).\\-]\\s*", "", ln) for ln in lines if not ln.startswith("#")]
    steps = [s for s in steps if s]
    if len(steps) <= 1:
        # Try splitting on numbered tokens within a single line
        parts = re.split(r"(?:(?<=\\s)|^)(?=\\d+[\\).]\\s+)", raw)
        parts = [re.sub(r"^[0-9]+[\\).\\-]\\s*", "", p).strip() for p in parts if p.strip()]
        if len(parts) > 1:
            steps = parts
        else:
            # Fallback split by semicolons or bullets
            parts = re.split(r"[;•]+", raw)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) > 1:
                steps = parts
    return steps[:max_steps]
