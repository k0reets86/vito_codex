"""image_utils — lightweight marketing image generator for platform bundles."""

from __future__ import annotations

from pathlib import Path
import textwrap
import hashlib

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # PIL optional
    Image = None
    ImageDraw = None
    ImageFont = None


def write_minimal_png(out_path: str) -> str:
    """Write a 1x1 PNG (transparent) to out_path."""
    # Precomputed 1x1 transparent PNG
    png_bytes = bytes([
        0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,
        0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,
        0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,
        0x08,0x06,0x00,0x00,0x00,0x1F,0x15,0xC4,0x89,
        0x00,0x00,0x00,0x0A,0x49,0x44,0x41,0x54,
        0x78,0x9C,0x63,0x00,0x01,0x00,0x00,0x05,0x00,0x01,
        0x0D,0x0A,0x2D,0xB4,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,0x44,0xAE,0x42,0x60,0x82
    ])
    Path(out_path).write_bytes(png_bytes)
    return out_path


def write_placeholder_png(out_path: str, width: int, height: int, text: str | None = None) -> str:
    """Write a styled marketing PNG of given size. Falls back to 1x1 if PIL unavailable."""
    if Image is None:
        return write_minimal_png(out_path)

    seed = hashlib.sha256(f"{width}x{height}:{text or ''}".encode("utf-8")).digest()
    base = (18 + seed[0] % 20, 28 + seed[1] % 28, 46 + seed[2] % 40)
    accent = (214 + seed[3] % 28, 145 + seed[4] % 60, 82 + seed[5] % 50)
    accent2 = (82 + seed[6] % 60, 186 + seed[7] % 50, 210 + seed[8] % 35)

    img = Image.new("RGB", (width, height), color=base)
    draw = ImageDraw.Draw(img)

    # layered background blocks
    draw.rectangle((0, 0, width, height), fill=base)
    draw.rounded_rectangle((int(width * 0.06), int(height * 0.08), int(width * 0.94), int(height * 0.92)), radius=28, fill=(248, 245, 239))
    draw.rounded_rectangle((int(width * 0.06), int(height * 0.08), int(width * 0.94), int(height * 0.19)), radius=24, fill=accent)
    draw.rounded_rectangle((int(width * 0.62), int(height * 0.28), int(width * 0.90), int(height * 0.78)), radius=22, fill=accent2)
    draw.rounded_rectangle((int(width * 0.10), int(height * 0.72), int(width * 0.56), int(height * 0.84)), radius=18, fill=(32, 40, 58))
    draw.ellipse((int(width * 0.70), int(height * 0.08), int(width * 0.92), int(height * 0.28)), fill=(255, 255, 255))

    if text:
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", max(28, width // 20))
        except Exception:
            title_font = ImageFont.load_default()
        try:
            body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(18, width // 40))
        except Exception:
            body_font = ImageFont.load_default()

        clean = " ".join(str(text).strip().split())
        lines = textwrap.wrap(clean, width=max(10, width // 24))[:3]
        y = int(height * 0.27)
        for line in lines:
            draw.text((int(width * 0.11), y), line, fill=(24, 24, 34), font=title_font)
            y += int(height * 0.09)

        sub = "Templates, prompts, workflows, and practical launch assets"
        sub_lines = textwrap.wrap(sub, width=max(14, width // 18))[:3]
        sy = int(height * 0.74)
        for line in sub_lines:
            draw.text((int(width * 0.13), sy), line, fill=(248, 245, 239), font=body_font)
            sy += int(height * 0.05)

        # fake preview cards
        card_x = int(width * 0.66)
        card_y = int(height * 0.34)
        card_w = int(width * 0.20)
        card_h = int(height * 0.10)
        for idx in range(3):
            yy = card_y + idx * int(card_h * 1.25)
            draw.rounded_rectangle((card_x, yy, card_x + card_w, yy + card_h), radius=14, fill=(250, 248, 244))
            draw.rectangle((card_x + 14, yy + 14, card_x + card_w - 14, yy + 24), fill=accent)
            draw.rectangle((card_x + 14, yy + 34, card_x + card_w - 42, yy + 42), fill=(190, 194, 201))
            draw.rectangle((card_x + 14, yy + 50, card_x + card_w - 72, yy + 58), fill=(210, 214, 220))

    img.save(out_path, format="PNG")
    return out_path
