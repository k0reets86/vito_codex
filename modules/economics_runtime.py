"""Deterministic pricing/margin helpers for EconomicsAgent."""

from __future__ import annotations

from typing import Any

PRODUCT_BANDS = {
    "digital_generic": {"economy": 9.0, "standard": 15.0, "premium": 24.0},
    "bundle": {"economy": 11.0, "standard": 18.0, "premium": 29.0},
    "journal": {"economy": 11.0, "standard": 17.0, "premium": 27.0},
    "planner": {"economy": 10.0, "standard": 16.0, "premium": 25.0},
    "course": {"economy": 19.0, "standard": 39.0, "premium": 79.0},
    "coloring_book": {"economy": 7.99, "standard": 10.99, "premium": 14.99},
}


def classify_product(product: str) -> str:
    low = str(product or "").lower()
    if "color" in low or "colour" in low:
        return "coloring_book"
    if any(k in low for k in ("bundle", "toolkit", "kit", "pack")):
        return "bundle"
    if "journal" in low:
        return "journal"
    if "planner" in low:
        return "planner"
    if any(k in low for k in ("course", "masterclass", "training", "system")):
        return "course"
    return "digital_generic"


def build_market_signal_pack(product: str) -> dict[str, Any]:
    kind = classify_product(product)
    band = PRODUCT_BANDS[kind]
    standard = float(band["standard"])
    return {
        "product_kind": kind,
        "price_band": dict(band),
        "competitor_anchor_range": [round(standard * 0.8, 2), round(standard * 1.2, 2)],
        "margin_assumptions": {
            "platform_fee_rate": 0.1,
            "refund_buffer_rate": 0.05,
            "traffic_cost_ratio": 0.3,
        },
        "pricing_mode": "conservative" if kind in {"coloring_book"} else "growth_standard",
    }


def build_pricing_confidence(product: str, scenario: dict[str, Any] | None = None) -> dict[str, Any]:
    signal = build_market_signal_pack(product)
    anchors = signal["competitor_anchor_range"]
    confidence = 0.72
    reasons = [
        f"product_kind={signal['product_kind']}",
        f"anchor_low={anchors[0]}",
        f"anchor_high={anchors[1]}",
    ]
    if scenario and scenario.get("units"):
        confidence += 0.06
        reasons.append("scenario_has_units")
    return {
        "confidence_score": round(min(confidence, 0.92), 2),
        "confidence_reasons": reasons,
        "fallback_mode": signal["pricing_mode"],
    }
