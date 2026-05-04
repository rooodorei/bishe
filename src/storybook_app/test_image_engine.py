"""测试绘图模块。

该模块提供和正式 `image_engine.generate_full_story_page()` 相同的函数签名，
但不会调用 ComfyUI，而是直接生成一张 PNG 占位图。

用途：
- 测试注册、登录、故事库、剧情生成、图片入库和前端展示流程。
- 节约调试时间，避免每次都等待真实绘图引擎。

切回正式绘图时，只需要把 `main.py` 中的导入改回：
`from .image_engine import generate_full_story_page`
"""

import struct
import zlib
from pathlib import Path

from .character_card import build_character_card, build_story_page_prompt, save_character_card
from .config import CHARACTER_CARD_OUTPUT_DIR, TEMP_OUTPUT_DIR


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """构造 PNG chunk。"""
    checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def _write_placeholder_png(path: Path, width: int = 640, height: int = 360) -> None:
    """使用标准库写出一张简单的 RGB PNG 占位图。"""
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            horizontal = x / max(width - 1, 1)
            vertical = y / max(height - 1, 1)

            r = int(255 - 42 * vertical)
            g = int(238 - 48 * horizontal)
            b = int(224 + 24 * vertical)

            if 48 < x < width - 48 and 48 < y < height - 48:
                border = x < 60 or x > width - 61 or y < 60 or y > height - 61
                if border:
                    r, g, b = 46, 196, 182

            if (x // 32 + y // 32) % 2 == 0 and 140 < x < width - 140 and 120 < y < height - 120:
                r = min(255, r + 8)
                g = min(255, g + 8)
                b = min(255, b + 8)

            row.extend((r, g, b))
        rows.append(bytes(row))

    raw_data = b"".join(rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _png_chunk(b"tEXt", "Description\0Test placeholder image generated without ComfyUI".encode("utf-8"))
    png += _png_chunk(b"IDAT", zlib.compress(raw_data, level=6))
    png += _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def generate_full_story_page(session_id, child_features, story_action, story_scene):
    """生成测试占位图，并返回临时图片路径。

    函数签名与正式绘图模块保持一致，方便 `main.py` 无缝切换。
    """
    card = build_character_card(child_features)
    save_character_card(card, CHARACTER_CARD_OUTPUT_DIR / f"character_card_{session_id}.json")
    positive, _negative = build_story_page_prompt(card, story_action, story_scene)
    print(f"[Test Stage 2 Prompt]: {positive}")

    final_page_path = TEMP_OUTPUT_DIR / "final_storybook_page.png"
    _write_placeholder_png(final_page_path)
    return str(final_page_path)
