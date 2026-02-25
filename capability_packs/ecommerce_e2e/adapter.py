# E-commerce E2E capability (stub)

def run(input_data: dict) -> dict:
    product = input_data.get("product")
    price = input_data.get("price")
    if not product or price is None:
        return {"status": "error", "error": "product_price_required"}
    return {"status": "ok", "output": {"listing": "draft", "product": product, "price": price}}
