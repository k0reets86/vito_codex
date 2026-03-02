#!/usr/bin/env python3
"""Боевой тест: анализ трендов → генерация продукта → публикация на Gumroad."""

import os

import asyncio
from pathlib import Path
from types import SimpleNamespace

from agents.content_creator import ContentCreator
from agents.ecommerce_agent import ECommerceAgent
from platforms.gumroad import GumroadPlatform
from modules.pdf_utils import write_minimal_pdf
from modules.image_utils import write_minimal_png


async def run_cycle():
    os.environ["AUTO_APPROVE_TESTS"] = "1"
    os.environ["VITO_ALLOW_MULTI"] = "1"
    os.environ["FAST_MODE"] = "1"
    # Minimal deps (no full VITO boot)
    async def _ok(*args, **kwargs):
        return True
    comms = SimpleNamespace(
        request_approval=_ok,
        request_approval_with_files=_ok,
    )
    content = ContentCreator(llm_router=None, memory=None, finance=None, comms=comms)
    ecommerce = ECommerceAgent(
        platforms={"gumroad": GumroadPlatform()},
        llm_router=None, memory=None, finance=None, comms=comms,
    )

    # 1) Topic
    topic = "AI Automation Checklist for Solopreneurs"

    # 2) Content creation (ebook draft)
    ebook = await content.create_ebook(topic=topic, chapters=3)
    text = ebook.output if ebook and ebook.success else f"{topic}\\nShort draft."
    out_dir = Path("/home/vito/vito-agent/output/boevoy")
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "product.pdf"
    write_minimal_pdf(text, str(pdf_path))

    # 3) Cover + thumbnail
    cover_path = out_dir / "cover.png"
    thumb_path = out_dir / "thumb.png"
    write_minimal_png(str(cover_path))
    write_minimal_png(str(thumb_path))

    # 4) Description
    desc = await content.create_product_description(product=topic, platform="gumroad")
    summary = ""
    description = ""
    if desc and desc.success:
        description = desc.output[:2000]
        summary = desc.output[:200]

    # 5) Publish
    data = {
        "name": topic[:80],
        "price": 9,
        "summary": summary,
        "description": description,
        "pdf_path": str(pdf_path),
        "cover_path": str(cover_path),
        "thumb_path": str(thumb_path),
    }
    publish = await ecommerce.create_listing("gumroad", data)
    print("PUBLISH RESULT:", getattr(publish, "output", None), getattr(publish, "error", None), flush=True)
    try:
        await ecommerce.platforms["gumroad"].close()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(run_cycle())
