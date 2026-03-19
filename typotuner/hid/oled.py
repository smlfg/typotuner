"""OLED display control for SteelSeries Apex Pro TKL 2023.

Protocol derived from steelseries-oled (edbgon/steelseries-oled):
- HID Feature Report with command byte 0x61
- 128x40 monochrome bitmap, 640 bytes (1 bit per pixel, row-major, MSB-first)
- Report structure: [report_id=0x00, cmd=0x61, bitmap[640], trailing=0x00]
- Total report size: 643 bytes
"""

from __future__ import annotations

from . import device

# OLED display dimensions
OLED_WIDTH = 128
OLED_HEIGHT = 40
OLED_PIXELS = OLED_WIDTH * OLED_HEIGHT  # 5120
OLED_DATA_SIZE = OLED_PIXELS // 8  # 640 bytes

# Protocol constants
OLED_CMD = 0x61
OLED_REPORT_ID = 0x00
OLED_REPORT_SIZE = 1 + 1 + OLED_DATA_SIZE + 1  # 643 bytes


def send_image(fd: int, bitmap: bytes) -> None:
    """Send a 640-byte monochrome bitmap to the OLED display.

    Args:
        fd: Open hidraw file descriptor (from device.open_device)
        bitmap: Exactly 640 bytes — 1 bit per pixel, row-major, MSB-first
                (matches PIL Image mode '1' tobytes() for 128x40)

    Raises:
        ValueError: If bitmap is not exactly 640 bytes
    """
    if len(bitmap) != OLED_DATA_SIZE:
        raise ValueError(f"Bitmap must be {OLED_DATA_SIZE} bytes, got {len(bitmap)}")

    report = bytearray(OLED_REPORT_SIZE)
    report[0] = OLED_REPORT_ID
    report[1] = OLED_CMD
    report[2 : 2 + OLED_DATA_SIZE] = bitmap
    # report[-1] already 0x00 (trailing byte)

    device.set_feature(fd, bytes(report))


def clear_screen(fd: int) -> None:
    """Clear the OLED display (all pixels off)."""
    send_image(fd, bytes(OLED_DATA_SIZE))


def render_text(text: str, font_size: int = 16) -> bytes:
    """Render a single line of text to a 128x40 monochrome bitmap.

    Args:
        text: Text to display
        font_size: Font size in pixels (default 16, good for single line)

    Returns:
        640-byte bitmap suitable for send_image()
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), color=0)
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    # Center vertically for single line
    bbox = draw.textbbox((0, 0), text, font=font)
    text_height = bbox[3] - bbox[1]
    y = max(0, (OLED_HEIGHT - text_height) // 2)
    draw.text((2, y), text, fill=1, font=font)

    return img.tobytes()


def render_multiline(lines: list[str], font_size: int = 12) -> bytes:
    """Render multiple lines of text to a 128x40 monochrome bitmap.

    Args:
        lines: Lines of text to render
        font_size: Font size in pixels (default 12 for multi-line)

    Returns:
        640-byte bitmap suitable for send_image()
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), color=0)
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    y = 1
    line_height = font_size + 2
    for line in lines:
        if y + line_height > OLED_HEIGHT:
            break
        draw.text((2, y), line, fill=1, font=font)
        y += line_height

    return img.tobytes()


def image_to_bitmap(img) -> bytes:
    """Convert a PIL Image to a 128x40 monochrome bitmap.

    Args:
        img: PIL Image (any mode — will be resized and converted)

    Returns:
        640-byte bitmap suitable for send_image()
    """
    img = img.resize((OLED_WIDTH, OLED_HEIGHT))
    img = img.convert("1")
    return img.tobytes()


def _load_font(size: int):
    """Load a monospace font, falling back through common paths."""
    from PIL import ImageFont

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()
