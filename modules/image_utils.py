"""image_utils — minimal PNG generator for placeholder images."""

from __future__ import annotations

from pathlib import Path

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
    """Write a simple placeholder PNG of given size. Falls back to 1x1 if PIL unavailable."""
    if Image is None:
        return write_minimal_png(out_path)
    img = Image.new("RGB", (width, height), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    if text:
        try:
            font = ImageFont.load_default()
            tw, th = draw.textsize(text, font=font)
            draw.text(((width - tw) / 2, (height - th) / 2), text, fill=(30, 30, 30), font=font)
        except Exception:
            pass
    img.save(out_path, format="PNG")
    return out_path
