"""转场类动效包：白闪 / 推镜 / 卡片翻 / 擦除 / 抖动切 / 穿镜 / 百叶 / 墨点扩散 / 暗场

统一契约：render(t, total, params) -> PIL.Image(1920x1080, RGB)
- t 是「转场内部」的相对秒数（0..total），total 一般 0.45-0.8 秒
- params.a_img / params.b_img：前后两帧的 PIL.Image（由 runtime 抽帧后传入）
- 没给图时用带编号的占位底，保证基准帧与回归测试永远能跑
- params.dur 可小于 total，超出部分保持终态（B 画面）

坑（已踩过）：
- 转场必须两端都是完整帧，别用被裁短的视频输入，否则 shortest 会截断整条链
- 抖动用确定性 sin，别用 random，否则同一时间码两次渲染不一致
- 白闪峰值别超过 0.12 秒，长了像掉帧
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from _core import AMBER, H, INK, MUTE, W, ease, font, paper

DEFAULT_DUR = 0.6


def _placeholder(label, tone=(222, 214, 194)):
    img = Image.new("RGB", (W, H), tone)
    d = ImageDraw.Draw(img)
    for y in range(0, H, 96):
        d.line([(0, y), (W, y)], fill=(206, 197, 176), width=1)
    d.text((W // 2, H // 2), label, font=font(160, bold=True), fill=INK, anchor="mm")
    d.text((W // 2, H // 2 + 170), "未提供 a_img / b_img，用占位帧",
           font=font(38), fill=MUTE, anchor="mm")
    return img


def _fit(src, w=W, h=H):
    if src is None:
        return None
    src = src.convert("RGB")
    k = max(w / src.width, h / src.height)
    src = src.resize((int(src.width * k) + 1, int(src.height * k) + 1), Image.LANCZOS)
    return src.crop(((src.width - w) // 2, (src.height - h) // 2,
                     (src.width - w) // 2 + w, (src.height - h) // 2 + h))


def _frames(p):
    a = _fit(p.get("a_img")) or _placeholder("A", (231, 224, 205))
    b = _fit(p.get("b_img")) or _placeholder("B", (208, 216, 214))
    return a, b


def _q(t, p):
    return ease(t / max(0.01, float(p.get("dur", DEFAULT_DUR))), p.get("ease", "inout"))


def _paste_shift(canvas, src, dx, dy=0):
    canvas.paste(src, (int(dx), int(dy)))


# ---------------------------------------------------------------- 1 白闪
def flash_white(t, total, params=None):
    p = {"dur": 0.48, "peak": 0.5}
    p.update(params or {})
    a, b = _frames(p)
    q = t / max(0.01, float(p["dur"]))
    if q <= 0:
        return a
    if q >= 1:
        return b
    peak = float(p["peak"])
    base = a if q < peak else b
    amp = (q / peak) if q < peak else (1 - q) / (1 - peak)
    amp = min(1.0, max(0.0, amp))
    white = Image.new("RGB", (W, H), (252, 250, 244))
    return Image.blend(base, white, amp ** 1.4)


# ---------------------------------------------------------------- 2 推镜
def push_slide(t, total, params=None):
    p = {"dur": 0.62, "axis": "x"}
    p.update(params or {})
    a, b = _frames(p)
    q = _q(t, p)
    out = paper((236, 230, 212))
    if p["axis"] == "y":
        _paste_shift(out, a, 0, -H * q)
        _paste_shift(out, b, 0, H * (1 - q))
        ImageDraw.Draw(out).line([(0, H * (1 - q)), (W, H * (1 - q))], fill=INK, width=10)
    else:
        _paste_shift(out, a, -W * q)
        _paste_shift(out, b, W * (1 - q))
        ImageDraw.Draw(out).line([(W * (1 - q) - 5, 0), (W * (1 - q) - 5, H)],
                                fill=INK, width=12)
    return out


# ---------------------------------------------------------------- 3 卡片翻
def card_flip(t, total, params=None):
    p = {"dur": 0.68, "squeeze": 0.86}
    p.update(params or {})
    a, b = _frames(p)
    q = min(1.0, max(0.0, t / float(p["dur"])))
    out = paper((235, 228, 210))
    half = float(p["squeeze"])
    if q < 0.5:
        k = 1 - 2 * q
        src = a
    else:
        k = 2 * q - 1
        src = b
    w = max(2, int(W * k))
    hh = max(2, int(H * (half + (1 - half) * k)))
    card = src.resize((w, hh), Image.LANCZOS)
    if k < 0.35:
        card = ImageEnhance.Brightness(card).enhance(0.55 + k)
    x = (W - w) // 2
    y = (H - hh) // 2
    shade = Image.new("L", (w + 40, hh + 40), 0)
    ImageDraw.Draw(shade).rectangle([20, 20, 20 + w, 20 + hh], fill=70)
    shade = shade.filter(ImageFilter.GaussianBlur(20))
    out.paste((0, 0, 0), (x - 20, y - 20), shade)
    out.paste(card, (x, y))
    return out


# ---------------------------------------------------------------- 4 擦除
def wipe_bar(t, total, params=None):
    p = {"dur": 0.58, "tilt": 90, "edge": AMBER}
    p.update(params or {})
    a, b = _frames(p)
    q = _q(t, p)
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    x = int((W + 260) * q) - 130
    tilt = int(p["tilt"])
    md.polygon([(x - tilt, 0), (x + tilt, 0), (x, H), (x - 2 * tilt, H)], fill=255)
    out = a.copy()
    out.paste(b, (0, 0), mask)
    if 0 < q < 1:
        od = ImageDraw.Draw(out)
        od.polygon([(x - tilt - 12, 0), (x + tilt - 12, 0),
                    (x - 12, H), (x - 2 * tilt - 12, H)], fill=tuple(p["edge"]))
    return out


# ---------------------------------------------------------------- 5 抖动切
def shake_cut(t, total, params=None):
    p = {"dur": 0.42, "amp": 26, "cut_at": 0.72}
    p.update(params or {})
    a, b = _frames(p)
    q = min(1.0, max(0.0, t / float(p["dur"])))
    if q >= float(p["cut_at"]):
        return b
    amp = float(p["amp"]) * (1 - q / float(p["cut_at"]))
    dx = int(math.sin(t * 61) * amp)
    dy = int(math.cos(t * 47) * amp * 0.55)
    out = paper((247, 242, 228))
    _paste_shift(out, a, dx, dy)
    d = ImageDraw.Draw(out)
    if dx > 0:
        d.rectangle([0, 0, dx, H], fill=(247, 242, 228))
    elif dx < 0:
        d.rectangle([W + dx, 0, W, H], fill=(247, 242, 228))
    return out


# ---------------------------------------------------------------- 6 穿镜
def zoom_through(t, total, params=None):
    p = {"dur": 0.64, "scale": 1.38}
    p.update(params or {})
    a, b = _frames(p)
    q = min(1.0, max(0.0, t / float(p["dur"])))
    s = float(p["scale"])
    if q < 0.5:
        k = 1 + (s - 1) * (q / 0.5)
        src, blur = a, (q / 0.5) * 8
    else:
        k = s - (s - 1) * ((q - 0.5) / 0.5)
        src, blur = b, (1 - q) / 0.5 * 8
    w, h = int(W * k), int(H * k)
    big = src.resize((w, h), Image.LANCZOS)
    if blur > 0.4:
        big = big.filter(ImageFilter.GaussianBlur(blur))
    return big.crop(((w - W) // 2, (h - H) // 2, (w - W) // 2 + W, (h - H) // 2 + H))


# ---------------------------------------------------------------- 7 百叶
def blinds(t, total, params=None):
    p = {"dur": 0.66, "n": 8}
    p.update(params or {})
    a, b = _frames(p)
    n = int(p["n"])
    cw = W // n
    out = a.copy()
    for i in range(n):
        qi = ease((t - i * (float(p["dur"]) * 0.42 / n)) / (float(p["dur"]) * 0.58))
        if qi <= 0:
            continue
        x = i * cw
        reveal = int(cw * qi)
        band = b.crop((x + (cw - reveal) // 2, 0, x + (cw - reveal) // 2 + reveal, H))
        out.paste(band, (x + (cw - reveal) // 2, 0))
    return out


# ---------------------------------------------------------------- 8 墨点扩散
def ink_spread(t, total, params=None):
    p = {"dur": 0.72, "cx": W // 2, "cy": H // 2, "ink": (26, 22, 16)}
    p.update(params or {})
    a, b = _frames(p)
    q = _q(t, p)
    cx, cy = int(p["cx"]), int(p["cy"])
    maxr = int(math.hypot(W, H))
    # 0.78 而非 1.0：中间态仍要露出四角的前一帧，否则看起来像硬切
    r = int(maxr * q * 0.78)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(3))
    out = a.copy()
    out.paste(b, (0, 0), mask)
    if 0 < q < 1:
        d = ImageDraw.Draw(out)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=tuple(p["ink"]), width=14)
    return out


# ---------------------------------------------------------------- 9 暗场
def fade_dip(t, total, params=None):
    p = {"dur": 0.58, "floor": 0.04}
    p.update(params or {})
    a, b = _frames(p)
    q = min(1.0, max(0.0, t / float(p["dur"])))
    floor = float(p["floor"])
    if q < 0.5:
        k = 1 - (1 - floor) * (q / 0.5)
        return ImageEnhance.Brightness(a).enhance(k)
    k = floor + (1 - floor) * ((q - 0.5) / 0.5)
    return ImageEnhance.Brightness(b).enhance(k)


ALL = ["flash_white", "push_slide", "card_flip", "wipe_bar", "shake_cut",
       "zoom_through", "blinds", "ink_spread", "fade_dip"]
