import pytest

from platforms.gumroad import GumroadPlatform


@pytest.mark.asyncio
async def test_gumroad_existing_update_requires_explicit_target():
    p = GumroadPlatform()
    out = await p.publish(
        {
            "allow_existing_update": True,
            "owner_edit_confirmed": True,
            "name": "Any",
            "description": "x",
            "price": 1,
        }
    )
    assert out.get("status") == "blocked"
    assert out.get("error") in {
        "create_mode_forbids_existing_update",
        "existing_update_requires_target_product_id_or_slug",
    }
    await p.close()
