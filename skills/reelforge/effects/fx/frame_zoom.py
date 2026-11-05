"""效果：屏幕边框 + 原位高亮 + 悬浮放大条

契约：render(t, total, params) -> PIL.Image（1920×1080, RGB）

设计要点（踩过坑总结）：
- 截图放进「显示器边框」，不强行铺满全屏
- 要强调的区域在原位画一个高亮框（不挪走画面）
- 放大条浮在高亮框上方，用一条细线连回原位；贴边时自动翻到下方
- 全程缓动：边框轻轻推入，放大条带轻微回弹冒出
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

DEFAULT_PARAMS = {
    "image": "",                      # 截图路径（必填）
    "focus": [100, 700, 900, 120],    # 要放大的区域 x,y,w,h（源图像素）
    "bg": [241, 235, 216],
    "ink": [26, 22, 16],
    "accent": [163, 74, 42],
    "screen": [190, 76, 1730, 756],   # 边框外框 x0,y0,x1,y1
    "bar_w": 1200,                    # 放大条宽度
    "inset": 14,
    "pan": 12,                        # 边框内画面的轻微位移
}


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _paper(w: int, h: int, bg) -> Image.Image:
    img = Image.new("RGB", (w, h), tuple(bg))
    wash = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(wash)
    d.ellipse([-w * 0.2, -h * 0.3, w * 1.2, h * 1.3], fill=28)
    wash = wash.filter(ImageFilter.GaussianBlur(240))
    darker = Image.new("RGB", (w, h), tuple(max(0, c - 8) for c in bg))
    return Image.composite(darker, img, wash)


def _shadow(w: int, h: int, radius: int, blur: int = 20, alpha: int = 64) -> Image.Image:
    m = Image.new("L", (w + blur * 2, h + blur * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([blur, blur, blur + w, blur + h], radius=radius, fill=alpha)
    return m.filter(ImageFilter.GaussianBlur(blur * 0.6))


def render(t: float, total: float, params: dict | None = None) -> Image.Image:
    p = dict(DEFAULT_PARAMS)
    p.update(params or {})
    if not p["image"]:
        raise ValueError("frame_zoom 需要 params['image']")

    src = Image.open(p["image"]).convert("RGB")
    sw, sh = src.size
    SX0, SY0, SX1, SY1 = p["screen"]
    inset = int(p["inset"])
    iw, ih = (SX1 - SX0) - inset * 2, (SY1 - SY0) - inset * 2
    k = min(iw / sw, ih / sh)
    cw, ch = int(sw * k), int(sh * k)
    content = src.resize((cw, ch), Image.LANCZOS)

    bx, by, bw, bh = p["focus"]
    bw, bh = min(bw, sw - bx), min(bh, sh - by)
    fx = inset + (iw - cw) // 2 + int(bx * k)
    fy = inset + (ih - ch) // 2 + int(by * k)
    fw, fh = max(40, int(bw * k)), max(24, int(bh * k))

    BAR_W = int(p["bar_w"])
    dw = BAR_W - 24
    dh = max(24, int(bh * (BAR_W / bw)))
    detail = src.crop((bx, by, bx + bw, by + bh)).resize((dw, dh), Image.LANCZOS)
    bar = Image.new("RGBA", (BAR_W, dh + 24), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    bd.rounded_rectangle([0, 0, BAR_W - 1, dh + 23], radius=22,
                         fill=(249, 244, 231, 255), outline=tuple(p["ink"]) + (255,), width=4)
    bar.paste(detail, ((BAR_W - dw) // 2, 12))

    img = _paper(1920, 1080, p["bg"]).convert("RGBA")
    q1 = _ease(t / 0.45)
    q2 = _ease(max(0.0, (t - 0.30) / 0.34))
    pop = 1 + 0.055 * (q2 * (1 - q2) * 4) if q2 > 0 else 0.0

    sx, sy = SX1 - SX0, SY1 - SY0
    ox, oy = SX0 - int((1 - q1) * 18), SY0 - int((1 - q1) * 12)
    pan = int(p["pan"] * q1)

    layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    layer.paste((0, 0, 0), (ox - 22, oy - 22), _shadow(sx, sy, 26, 22, 60))
    layer.paste(Image.new("RGB", (sx, sy), (250, 246, 235)), (ox, oy))
    layer.paste(content, (ox + inset + (iw - cw) // 2, oy + inset + (ih - ch) // 2 - pan))
    ImageDraw.Draw(layer).rounded_rectangle([ox, oy, ox + sx - 1, oy + sy - 1], radius=26,
                                            outline=tuple(p["ink"]) + (int(255 * q1),), width=6)
    img.alpha_composite(layer)

    if q2 > 0:
        sc = q2 * pop
        bb = bar.resize((max(8, int(BAR_W * sc)), max(8, int((dh + 24) * sc))), Image.LANCZOS)
        fcx = ox + fx + fw // 2
        fcy = oy + fy + fh // 2 - pan
        px = fcx - bb.width // 2
        py = fcy - fh // 2 - bb.height - 26
        if py < SY0 + 16:
            py = fcy + fh // 2 + 26
        px = max(SX0 + 16, min(SX1 - 16 - bb.width, px))
        py = max(SY0 + 16, min(SY1 - 16 - bb.height, py))

        over = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        od = ImageDraw.Draw(over)
        al = int(235 * q2)
        od.rectangle([ox + fx, oy + fy - pan, ox + fx + fw, oy + fy + fh - pan],
                     outline=tuple(p["accent"]) + (al,), width=3)
        cx = ox + fx + fw // 2
        if py + bb.height < oy + fy - pan:
            od.line([(cx, py + bb.height), (cx, oy + fy - pan)], fill=tuple(p["accent"]) + (al,), width=2)
        else:
            od.line([(cx, oy + fy + fh - pan), (cx, py)], fill=tuple(p["accent"]) + (al,), width=2)
        over.paste((0, 0, 0), (px - 18, py - 18), _shadow(bb.width, bb.height, 20, 18, 70))
        over.alpha_composite(bb, (px, py))
        img.alpha_composite(over)

    return img.convert("RGB")
