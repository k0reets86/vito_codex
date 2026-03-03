"""ImageGenerator — unified wrapper for image generation APIs.

Supports: Replicate (SDXL, Flux), BFL (Flux Pro), WaveSpeed (fast/cheap), DALL-E (OpenAI).
Auto-selects best service based on task type and budget.
Uploads results to Cloudinary CDN.
"""

import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any, Optional

import aiohttp

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings

logger = get_logger("image_gen", agent="image_generator")

OUTPUT_DIR = PROJECT_ROOT / "output" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class ImageGenerator:
    """Smart router for image generation APIs."""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._service_status: dict[str, dict] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ── Service availability check ──────────────────────────────────

    async def check_services(self) -> dict[str, dict]:
        """Check which image services are available and their status."""
        services = {}

        if settings.REPLICATE_API_TOKEN:
            try:
                session = await self._get_session()
                async with session.get(
                    "https://api.replicate.com/v1/account",
                    headers={"Authorization": f"Bearer {settings.REPLICATE_API_TOKEN}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        services["replicate"] = {"available": True, "models": [
                            "black-forest-labs/flux-schnell",  # fast, cheap
                            "stability-ai/sdxl",              # high quality
                        ]}
                    else:
                        services["replicate"] = {"available": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                services["replicate"] = {"available": False, "error": str(e)}

        if settings.BFL_API_KEY:
            services["bfl"] = {"available": True, "models": ["flux-pro-1.1"]}

        if settings.WAVESPEED_API_KEY:
            services["wavespeed"] = {"available": True, "models": ["flux-dev"]}

        if settings.OPENAI_API_KEY:
            services["dalle"] = {"available": True, "models": ["dall-e-3"]}

        self._service_status = services
        return services

    def select_service(self, style: str = "photo", fast: bool = False, cheap: bool = False) -> str:
        """Select best service for the task.

        style: "photo" (photorealism), "art" (illustration), "logo", "meme"
        fast: prioritize speed
        cheap: prioritize cost
        """
        available = {k: v for k, v in self._service_status.items() if v.get("available")}
        if not available:
            return ""

        # Priority logic (no LLM needed — pure code)
        if cheap and "wavespeed" in available:
            return "wavespeed"
        if fast and "wavespeed" in available:
            return "wavespeed"
        if style in ("photo", "product") and "replicate" in available:
            return "replicate"
        if style in ("art", "illustration") and "bfl" in available:
            return "bfl"
        if style == "logo" and "dalle" in available:
            return "dalle"
        if "replicate" in available:
            return "replicate"
        if "bfl" in available:
            return "bfl"
        if "wavespeed" in available:
            return "wavespeed"
        if "dalle" in available:
            return "dalle"
        return ""

    # ── Generation methods ──────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        style: str = "photo",
        width: int = 1024,
        height: int = 1024,
        service: str = "",
        filename: str = "",
    ) -> dict[str, Any]:
        """Generate image. Returns {path, url, service, cost_usd, error}."""
        if not self._service_status:
            await self.check_services()

        if not service:
            service = self.select_service(style=style)
        if not service:
            return {"error": "No image generation service available", "path": "", "url": ""}

        logger.info(
            f"Генерация изображения: service={service}, style={style}",
            extra={"event": "image_gen_start", "context": {"service": service, "prompt": prompt[:100]}},
        )

        try:
            if service == "replicate":
                return await self._generate_replicate(prompt, width, height, style, filename)
            elif service == "bfl":
                return await self._generate_bfl(prompt, width, height, filename)
            elif service == "wavespeed":
                return await self._generate_wavespeed(prompt, width, height, filename)
            elif service == "dalle":
                return await self._generate_dalle(prompt, width, height, filename)
            else:
                return {"error": f"Unknown service: {service}", "path": "", "url": ""}
        except Exception as e:
            logger.error(f"Image generation error ({service}): {e}", exc_info=True)
            return {"error": str(e), "path": "", "url": "", "service": service}

    async def _generate_replicate(
        self, prompt: str, width: int, height: int, style: str, filename: str
    ) -> dict:
        """Replicate API — supports SDXL and Flux models."""
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {settings.REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        }

        # Choose model based on style
        model = "black-forest-labs/flux-schnell"  # fast, ~$0.003
        if style in ("photo", "product"):
            model = "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"

        payload = {
            "version": model.split(":")[-1] if ":" in model else None,
            "input": {"prompt": prompt, "width": width, "height": height},
        }

        # For flux-schnell, use the deployments endpoint
        if "flux-schnell" in model:
            url = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
            payload = {"input": {"prompt": prompt, "go_fast": True, "num_outputs": 1}}
        else:
            url = "https://api.replicate.com/v1/predictions"

        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
            if resp.status not in (200, 201):
                return {"error": f"Replicate: {data.get('detail', resp.status)}", "path": "", "url": ""}

        # Poll for result
        prediction_url = data.get("urls", {}).get("get", "")
        if not prediction_url:
            prediction_url = f"https://api.replicate.com/v1/predictions/{data['id']}"

        for _ in range(60):  # max 60 seconds
            await asyncio.sleep(2)
            async with session.get(prediction_url, headers=headers) as resp:
                result = await resp.json()
                status = result.get("status")
                if status == "succeeded":
                    output = result.get("output")
                    image_url = output[0] if isinstance(output, list) else output
                    path = await self._download_image(image_url, filename or f"replicate_{int(time.time())}.png")
                    cdn_url = await self._upload_cloudinary(path) if path else ""
                    return {
                        "path": str(path) if path else "",
                        "url": cdn_url or image_url,
                        "service": "replicate",
                        "model": model.split("/")[-1].split(":")[0],
                        "cost_usd": 0.003,
                    }
                elif status == "failed":
                    return {"error": f"Replicate failed: {result.get('error')}", "path": "", "url": ""}

        return {"error": "Replicate timeout", "path": "", "url": ""}

    async def _generate_bfl(self, prompt: str, width: int, height: int, filename: str) -> dict:
        """BFL (Black Forest Labs) Flux Pro API."""
        session = await self._get_session()
        headers = {"X-Key": settings.BFL_API_KEY, "Content-Type": "application/json"}

        # Step 1: Create generation task
        payload = {
            "prompt": prompt,
            "width": width,
            "height": height,
        }
        async with session.post(
            "https://api.bfl.ml/v1/flux-pro-1.1",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                return {"error": f"BFL: {data}", "path": "", "url": ""}
            task_id = data.get("id")

        # Step 2: Poll for result
        for _ in range(60):
            await asyncio.sleep(2)
            async with session.get(
                f"https://api.bfl.ml/v1/get_result?id={task_id}",
                headers=headers,
            ) as resp:
                result = await resp.json()
                status = result.get("status")
                if status == "Ready":
                    image_url = result.get("result", {}).get("sample", "")
                    if image_url:
                        path = await self._download_image(
                            image_url, filename or f"bfl_{int(time.time())}.png"
                        )
                        cdn_url = await self._upload_cloudinary(path) if path else ""
                        return {
                            "path": str(path) if path else "",
                            "url": cdn_url or image_url,
                            "service": "bfl",
                            "model": "flux-pro-1.1",
                            "cost_usd": 0.04,
                        }
                elif status in ("Error", "Failed"):
                    return {"error": f"BFL failed: {result}", "path": "", "url": ""}

        return {"error": "BFL timeout", "path": "", "url": ""}

    async def _generate_wavespeed(self, prompt: str, width: int, height: int, filename: str) -> dict:
        """WaveSpeed AI — fast and cheap generation."""
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {settings.WAVESPEED_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "prompt": prompt,
            "size": f"{width}x{height}",
        }

        async with session.post(
            "https://api.wavespeed.ai/api/v3/wavespeed-ai/flux-dev/generate",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                return {"error": f"WaveSpeed: {data}", "path": "", "url": ""}

        # Poll or get direct result
        request_id = data.get("data", {}).get("id", "")
        if not request_id:
            # Direct result
            outputs = data.get("data", {}).get("outputs", [])
            if outputs:
                image_url = outputs[0]
                path = await self._download_image(image_url, filename or f"wavespeed_{int(time.time())}.png")
                cdn_url = await self._upload_cloudinary(path) if path else ""
                return {"path": str(path) if path else "", "url": cdn_url or image_url, "service": "wavespeed", "cost_usd": 0.01}

        # Poll
        for _ in range(60):
            await asyncio.sleep(2)
            async with session.get(
                f"https://api.wavespeed.ai/api/v3/predictions/{request_id}/result",
                headers=headers,
            ) as resp:
                result = await resp.json()
                status = result.get("data", {}).get("status", "")
                if status == "completed":
                    outputs = result.get("data", {}).get("outputs", [])
                    if outputs:
                        image_url = outputs[0]
                        path = await self._download_image(image_url, filename or f"wavespeed_{int(time.time())}.png")
                        cdn_url = await self._upload_cloudinary(path) if path else ""
                        return {"path": str(path) if path else "", "url": cdn_url or image_url, "service": "wavespeed", "cost_usd": 0.01}
                elif status in ("failed", "error"):
                    return {"error": f"WaveSpeed failed: {result}", "path": "", "url": ""}

        return {"error": "WaveSpeed timeout", "path": "", "url": ""}

    async def _generate_dalle(self, prompt: str, width: int, height: int, filename: str) -> dict:
        """DALL-E 3 via OpenAI API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # DALL-E 3 supports: 1024x1024, 1024x1792, 1792x1024
        size = "1024x1024"
        if width > height:
            size = "1792x1024"
        elif height > width:
            size = "1024x1792"

        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        path = await self._download_image(image_url, filename or f"dalle_{int(time.time())}.png")
        cdn_url = await self._upload_cloudinary(path) if path else ""

        return {
            "path": str(path) if path else "",
            "url": cdn_url or image_url,
            "service": "dalle",
            "model": "dall-e-3",
            "cost_usd": 0.04,  # standard quality
        }

    # ── Helpers ─────────────────────────────────────────────────────

    async def _download_image(self, url: str, filename: str) -> Optional[Path]:
        """Download image to output/images/."""
        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    path = OUTPUT_DIR / filename
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    logger.info(f"Image saved: {path}", extra={"event": "image_saved"})
                    return path
        except Exception as e:
            logger.error(f"Image download error: {e}", extra={"event": "image_download_error"})
        return None

    async def _upload_cloudinary(self, path: Optional[Path]) -> str:
        """Upload image to Cloudinary CDN. Returns URL or empty string."""
        if not path or not path.exists():
            return ""
        if not all([settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET]):
            return ""

        try:
            import hashlib
            timestamp = str(int(time.time()))
            # Sign ALL params alphabetically (except file, api_key, resource_type)
            to_sign = f"folder=vito&timestamp={timestamp}{settings.CLOUDINARY_API_SECRET}"
            signature = hashlib.sha1(to_sign.encode()).hexdigest()

            session = await self._get_session()
            form = aiohttp.FormData()
            form.add_field("file", open(path, "rb"), filename=path.name)
            form.add_field("api_key", settings.CLOUDINARY_API_KEY)
            form.add_field("timestamp", timestamp)
            form.add_field("signature", signature)
            form.add_field("folder", "vito")

            async with session.post(
                f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload",
                data=form,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cdn_url = data.get("secure_url", "")
                    logger.info(f"Cloudinary upload OK: {cdn_url}", extra={"event": "cloudinary_upload_ok"})
                    return cdn_url
                else:
                    body = await resp.text()
                    logger.warning(f"Cloudinary upload failed: {resp.status} {body[:200]}")
        except Exception as e:
            logger.error(f"Cloudinary upload error: {e}", exc_info=True)
        return ""

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
