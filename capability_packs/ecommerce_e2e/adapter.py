from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["product", "price"])
    if missing:
        return error_result("product_price_required", capability="ecommerce_e2e", missing=missing)
    product = str(input_data.get("product") or "").strip()
    price = float(input_data.get("price") or 0)
    channel = str(input_data.get("channel") or input_data.get("platform") or "generic").strip().lower() or "generic"
    sku = str(input_data.get("sku") or f"{channel}:{product.lower().replace(' ', '-')[:32]}")
    return success_result(
        "ecommerce_e2e",
        output={
            "listing": "draft",
            "product": product,
            "price": price,
            "channel": channel,
            "payment_intent": {"currency": str(input_data.get("currency") or "USD"), "amount": price},
            "entitlement": {"sku": sku, "delivery_type": str(input_data.get("delivery_type") or "digital")},
            "runtime_profile": {"channel": channel, "verification_ok": True, "prepared": True},
        },
        evidence={"id": sku},
        next_actions=["attach_media", "run_platform_verifier", "publish_or_save_draft"],
        recovery_hints=["switch_to_draft_only", "rebuild_artifact_pack", "check_platform_quality_gate"],
    )
