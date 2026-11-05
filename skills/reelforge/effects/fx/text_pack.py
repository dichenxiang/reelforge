"""文本类动效包：逐字升起 / 双色块对句 / 柔焦淡入 / 荧光笔 / 数字滚动 / 印章砸下

每个函数签名一致：render(t, total, params) -> PIL.Image(1920×1080, RGB)
t 为当前秒数，total 为该镜总时长。
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from _core import (H, W, ease, font, paper, shadow, text_w, wrap)

INK = (26, 22, 16)
AMBER = (163, 74, 42)
MUTE = (120, 112, 96)


def _base(p):
    img = paper(tuple(p.get("bg", (241, 235, 216))))
    return img, ImageDraw.Draw(img)


# ---------------------------------------------------------------- 逐字升起
def char_rise(t, total, params=None):
    p = {"text": "一句话，说清一件事", "size": 92, "y": 520, "stagger": 0.035,
         "dur": 0.42, "color": INK}
    p.update(params or {})
    img, d = _base(p)
    f = font(int(p["size"]), bold=True)
    s = p["text"]
    total_w = sum(text_w(d, ch, f) for ch in s)
    x = (W - total_w) // 2
    for i, ch in enumerate(s):
        q = ease((t - i * p["stagger"]) / p["dur"])
        if q <= 0:
            x += text_w(d, ch, f)
            continue
        dy = int((1 - q) * p["size"] * 0.55)
        a = int(255 * q)
        layer = Image.new("RGBA", (text_w(d, ch, f) + 40, int(p["size"] * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((20, 20 + dy), ch, font=f, fill=tuple(p["color"]) + (a,))
        img.paste(layer, (x - 20, int(p["y"] - p["size"] * 1.6 / 2)), layer)
        x += text_w(d, ch, f)
    return img


# ---------------------------------------------------------------- 双色块对句
def double_block_lines(t, total, params=None):
    p = {"lines": ["不是模型不行", "是你没说清楚"], "size": 84, "gap": 150, "y": 470,
         "block": (26, 22, 16), "alt": (250, 246, 235), "color": (250, 246, 235),
         "color2": (26, 22, 16)}
    p.update(params or {})
    img, d = _base(p)
    f = font(int(p["size"]), bold=True)
    for i, line in enumerate(p["lines"][:2]):
        tw = text_w(d, line, f)
        q = ease((t - i * 0.12) / 0.26)
        if q <= 0:
            continue
        bw = int((tw + 96) * q)
        by = int(p["y"] + i * p["gap"])
        bg = p["block"] if i == 0 else p["alt"]
        fg = p["color"] if i == 0 else p["color2"]
        box = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        bx0 = (W - tw - 96) // 2
        bd.rectangle([bx0, by - 14, bx0 + bw, by + int(p["size"] * 1.30)],
                     fill=tuple(bg) + (255,))
        if i == 1:
            bd.rectangle([bx0, by - 14, bx0 + bw, by + int(p["size"] * 1.30)],
                         outline=tuple(MUTE) + (255,), width=2)
        img.alpha_composite(box) if img.mode == "RGBA" else img.paste(box, (0, 0), box)
        # 文字按块宽裁切，形成"被刷出来"的效果
        tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(tl).text(((W - tw) // 2, by), line, font=f, fill=tuple(fg) + (255,))
        if bw < tw + 70:
            m = Image.new("L", (W, H), 0)
            ImageDraw.Draw(m).rectangle([0, 0, bx0 + bw - 26, H], fill=255)
            tl.putalpha(Image.composite(tl.getchannel("A"), Image.new("L", (W, H), 0), m))
        img.paste(tl, (0, 0), tl)
    return img


# ---------------------------------------------------------------- 柔焦淡入
def blur_focus_in(t, total, params=None):
    p = {"text": "它得自己猜光线、猜机位", "size": 88, "y": 520, "dur": 0.9, "color": INK}
    p.update(params or {})
    base, d = _base(p)
    f = font(int(p["size"]), bold=True)
    q = ease(t / p["dur"], "out")
    a = int(255 * q)
    blur = (1 - q) * int(p["size"] / 6)
    dy = int((1 - q) * p["size"] * 0.22)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((W // 2, p["y"] + dy), p["text"], font=f,
                               fill=tuple(p["color"]) + (a,), anchor="mm")
    if blur > 0.4:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    base.paste(layer, (0, 0), layer)
    return base


# ---------------------------------------------------------------- 荧光笔划重点
def marker_highlight(t, total, params=None):
    p = {"text": "只给了一句话", "size": 96, "y": 520, "color": INK,
         "mark": (226, 190, 66), "delay": 0.25}
    p.update(params or {})
    img, d = _base(p)
    f = font(int(p["size"]), bold=True)
    tw = text_w(d, p["text"], f)
    x0 = (W - tw) // 2
    q = ease((t - p["delay"]) / 0.35)
    if q > 0:
        # 手绘感的粗马克笔条：略微倾斜、两端不齐
        bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar)
        hgt = int(p["size"] * 0.58)
        yb = int(p["y"] + p["size"] * 0.30)
        bd.polygon([(x0 - 14, yb + 8), (x0 + int((tw + 30) * q), yb - 4),
                    (x0 + int((tw + 30) * q), yb + hgt - 2), (x0 - 14, yb + hgt + 6)],
                   fill=tuple(p["mark"]) + (200,))
        bar = bar.filter(ImageFilter.GaussianBlur(1.2))
        img.paste(bar, (0, 0), bar)
    d.text((W // 2, p["y"] + p["size"] * 0.42), p["text"], font=f, fill=tuple(p["color"]),
           anchor="mm")
    return img


# ---------------------------------------------------------------- 数字滚动
def count_up(t, total, params=None):
    p = {"value": 1280, "unit": "字", "label": "一份提示词", "size": 200,
         "dur": 1.1, "color": INK}
    p.update(params or {})
    img, d = _base(p)
    q = ease(t / p["dur"], "out")
    val = int(p["value"] * q)
    f = font(int(p["size"]), bold=True)
    fs = font(48, bold=False)
    d.text((W // 2, p["label"] and 400 or 480), p["label"], font=fs, fill=MUTE, anchor="mm")
    nw = text_w(d, str(val), f)
    uw = text_w(d, p["unit"], fs)
    total_w = nw + uw + 12
    d.text(((W - total_w) // 2, 560), str(val), font=f, fill=tuple(p["color"]), anchor="ls")
    d.text(((W - total_w) // 2 + nw + 12, 560), p["unit"], font=fs, fill=AMBER, anchor="ls")
    return img


# ---------------------------------------------------------------- 印章砸下
def stamp_slam(t, total, params=None):
    p = {"text": "已确认", "size": 120, "y": 560, "color": (176, 48, 40), "delay": 0.18}
    p.update(params or {})
    img, d = _base(p)
    q = ease((t - p["delay"]) / 0.32, "out")
    if q <= 0:
        return img
    sc = 1.7 - 0.7 * q
    a = int(235 * min(1.0, q * 1.6))
    size = int(p["size"])
    f = font(size, bold=True)
    tw = text_w(d, p["text"], f)
    bw, bh = tw + 80, size + 80
    seal = Image.new("RGBA", (bw + 40, bh + 40), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seal)
    sd.rounded_rectangle([20, 20, 20 + bw, 20 + bh], radius=18,
                         outline=tuple(p["color"]) + (a,), width=10)
    sd.text((20 + bw // 2, 20 + bh // 2), p["text"], font=f,
            fill=tuple(p["color"]) + (a,), anchor="mm")
    seal = seal.rotate(-7, expand=False, resample=Image.BICUBIC)
    seal = seal.resize((int(seal.width * sc), int(seal.height * sc)), Image.LANCZOS)
    if q < 0.85:
        seal = seal.filter(ImageFilter.GaussianBlur((1 - q) * 6))
    img.paste(seal, (W // 2 - seal.width // 2, int(p["y"]) - seal.height // 2), seal)
    return img
