from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable


QUALITY_REQUIRED_ACTIONS = {
    "publish",
    "listing_create",
    "listing_update",
    "product_create",
    "content_publish",
}


def quality_gate(actions: set[str] | None = None):
    """Decorator that marks agent methods as quality-gated runtime paths."""

    required = set(actions or QUALITY_REQUIRED_ACTIONS)

    def _decorator(fn: Callable[..., Awaitable[Any]]):
        @wraps(fn)
        async def _wrapped(*args, **kwargs):
            return await fn(*args, **kwargs)

        setattr(_wrapped, "__quality_gate__", True)
        setattr(_wrapped, "__quality_gate_actions__", sorted(required))
        return _wrapped

    return _decorator

