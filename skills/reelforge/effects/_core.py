"""效果库公共核心：纸张、字体、缓动、卡片、阴影。

只放「多个效果都会用到」的最小件，不放任何具体效果。
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080

# 常见中文字体，按优先级尝试；找不到就用 PIL 默认
FONT_CANDIDATES = [
    ("C:/Windows/Fonts/SourceHanSerifSC-Bold.otf", 0),
    ("C:/Windows/Fonts/SourceHanSerifSC-Regular.otf", 0),
    ("C:/Windows/Fonts/NotoSerifCJKsc-Bold.otf", 0),
    ("C:/Windows/Fonts/simsun.ttc", 0),
    ("C:/Windows/Fonts/msyhbd.ttc", 0),
    ("C:/Windows/Fonts/msyh.ttc", 0),
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", 0),
]


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    order = FONT_CANDIDATES if bold else list(reversed(FONT_CANDIDATES))
    for path, idx in order:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default()


def ease(x: float, kind: str = "out") -> float:
    x = max(0.0, min(1.0, x))
    if kind == "out":
        return 1 - (1 - x) ** 3
    if kind == "in":
        return x ** 3
    if kind == "inout":
        return 3 * x * x - 2 * x * x * x
    if kind == "back":                     # 轻微回弹
        c = 1.70158
        return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2
    return x


def paper(bg=(241, 235, 216), vignette: int = 26) -> Image.Image:
    """纸底：底色 + 很轻的暗角，不抢文字。"""
    img = Image.new("RGB", (W, H), tuple(bg))
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-W * 0.18, -H * 0.28, W * 1.18, H * 1.28], fill=vignette)
    mask = mask.filter(ImageFilter.GaussianBlur(240))
    darker = Image.new("RGB", (W, H), tuple(max(0, c - 9) for c in bg))
    return Image.composite(darker, img, mask)


def shadow(w: int, h: int, radius: int, blur: int = 20, alpha: int = 64) -> Image.Image:
    m = Image.new("L", (w + blur * 2, h + blur * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([blur, blur, blur + w, blur + h], radius=radius, fill=alpha)
    return m.filter(ImageFilter.GaussianBlur(blur * 0.6))


def text_w(d: ImageDraw.ImageDraw, s: str, f: ImageFont.FreeTypeFont) -> int:
    return int(d.textlength(s, font=f))


def draw_text(d, xy, s, f, fill, anchor="la"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def center_text(img: Image.Image, s: str, f, fill, cy: int, cx: int | None = None):
    d = ImageDraw.Draw(img)
    d.text((cx if cx is not None else W // 2, cy), s, font=f, fill=fill, anchor="mm")
    return d


def wrap(d: ImageDraw.ImageDraw, s: str, f, max_w: int) -> list[str]:
    """按宽度折行（中文逐字测宽）。"""
    lines, cur = [], ""
    for ch in s:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if text_w(d, cur + ch, f) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def ink_rgba(color=(26, 22, 16), a: int = 255):
    return tuple(color) + (a,)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def wiggle(seed: int, t: float, amp: float = 1.0) -> float:
    return math.sin(t * 6.28 + seed * 1.7) * amp
