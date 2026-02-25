import pytest

from modules.platform_smoke import PlatformSmoke


class _P:
    def __init__(self, ok=True):
        self.ok = ok

    async def authenticate(self):
        return self.ok

    async def get_analytics(self):
        return {"x": 1}

    async def get_products(self):
        return [{"id": 1}]


@pytest.mark.asyncio
async def test_platform_smoke_ok():
    sm = PlatformSmoke({"gumroad": _P(ok=True)})
    rows = await sm.run(["gumroad"])
    assert len(rows) == 1
    assert rows[0]["status"] == "success"


@pytest.mark.asyncio
async def test_platform_smoke_fail():
    sm = PlatformSmoke({"etsy": _P(ok=False)})
    rows = await sm.run(["etsy"])
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
