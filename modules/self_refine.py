"""Self-refine helper for LLM outputs (optional, gated by settings)."""
from __future__ import annotations

from typing import Optional

from config.logger import get_logger

logger = get_logger("self_refine", agent="self_refine")


async def refine_once(llm_router, task_type, draft: str, context: str = "") -> Optional[str]:
    """Run a single self-refine pass on draft text."""
    if not draft:
        return None
    prompt = (
        "You are a critical editor. Improve the draft below while preserving facts and intent.\n"
        "Rules:\n"
        "- Do not invent facts.\n"
        "- Keep it concise and actionable.\n"
        "- Preserve key constraints.\n\n"
        f"{context}\n"
        "DRAFT:\n"
        f"{draft}\n\n"
        "Return the improved version only."
    )
    try:
        refined = await llm_router.call_llm(
            task_type=task_type,
            prompt=prompt,
            estimated_tokens=800,
        )
        return refined or None
    except Exception as e:
        logger.warning(f"self_refine failed: {e}", extra={"event": "self_refine_failed"})
        return None

