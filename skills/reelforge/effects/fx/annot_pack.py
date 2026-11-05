"""标注类动效包：引出线 / 圆圈 / 聚光压暗 / 箭头 / 角标框 / 序号徽章 / 下划线扫过

统一约定：
- 画布 1920×1080
- target = [x, y, w, h] 指向要标注的区域（画布坐标）
- image 可选：给了就把图铺满画布当底，标注叠在上面；没给就用纸底
- 所有动效都在前 0.6–0.9 秒内完成，之后保持，方便叠加在其他镜头上
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from _core import AMBER, H, INK, MUTE, W, ease, font, paper, text_w

DOT = (176, 48, 40)


def _canvas(p):
    img_path = p.get("image")
    if img_path:
        try:
            src = Image.open(img_path).convert("RGB")
            k = max(W / src.width, H / src.height)
            src = src.resize((int(src.width * k) + 1, int(src.height * k) + 1), Image.LANCZOS)
            img = src.crop(((src.width - W) // 2, (src.height - H) // 2,
                            (src.width - W) // 2 + W, (src.height - H) // 2 + H))
            return img, ImageDraw.Draw(img)
        except Exception:
            pass
    img = paper(tuple(p.get("bg", (241, 235, 216))))
    return img, ImageDraw.Draw(img)


def _tgt(p):
    x, y, w, h = p.get("target", [700, 420, 520, 240])
    return int(x), int(y), int(w), int(h)


# ---------------------------------------------------------------- 引出线
def callout_line(t, total, params=None):
    p = {"target": [820, 470, 280, 120], "label": "看这里", "side": "right",
         "dot_at": [0.5, 0.5], "color": DOT, "size": 34}
    p.update(params or {})
    img, d = _canvas(p)
    tx, ty, tw, th = _tgt(p)
    dx = tx + int(tw * p["dot_at"][0])
    dy = ty + int(th * p["dot_at"][1])

    q1 = ease(t / 0.22)                                  # 圆点 + 涟漪
    if q1 > 0:
        r = int(9 * q1)
        d.ellipse([dx - r, dy - r, dx + r, dy + r], fill=tuple(p["color"]) + (255,))
        for k in range(2):
            rq = ease((t - 0.10 - k * 0.12) / 0.5)
            if 0 < rq < 1:
                rr = int(12 + 46 * rq)
                d.ellipse([dx - rr, dy - rr, dx + rr, dy + rr],
                          outline=tuple(p["color"]) + (int(150 * (1 - rq)),), width=2)

    f = font(int(p["size"]), bold=True)
    lw = text_w(d, p["label"], f) + 36
    lh = int(p["size"] * 1.7)
    if p["side"] == "right":
        lx, ly = dx + 120, dy - lh // 2
    else:
        lx, ly = dx - 120 - lw, dy - lh // 2

    q2 = ease((t - 0.22) / 0.28)                          # 折线生长
    if q2 > 0:
        elbow = (dx + (60 if p["side"] == "right" else -60), dy)
        pts = []
        seg1 = [(dx, dy), elbow]
        seg2 = [elbow, (lx if p["side"] == "right" else lx + lw, ly + lh // 2)]
        if q2 <= 0.5:
            k = q2 / 0.5
            pts = [seg1[0], (seg1[0][0] + (seg1[1][0] - seg1[0][0]) * k,
                             seg1[0][1] + (seg1[1][1] - seg1[0][1]) * k)]
        else:
            k = (q2 - 0.5) / 0.5
            pts = seg1 + [(seg2[0][0] + (seg2[1][0] - seg2[0][0]) * k,
                           seg2[0][1] + (seg2[1][1] - seg2[0][1]) * k)]
        if len(pts) >= 2:
            d.line(pts, fill=tuple(p["color"]) + (235,), width=3, joint="curve")

    q3 = ease((t - 0.44) / 0.26)                          # 标签遮罩揭示
    if q3 > 0:
        box = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        bd.rounded_rectangle([lx, ly, lx + lw, ly + lh], radius=8,
                             fill=(250, 246, 235, 250), outline=tuple(INK) + (255,), width=2)
        bd.text((lx + 18, ly + lh // 2), p["label"], font=f, fill=tuple(INK) + (255,), anchor="lm")
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).rectangle([lx - 2, 0, lx - 2 + int((lw + 4) * q3), H], fill=255)
        box.putalpha(Image.composite(box.getchannel("A"), Image.new("L", (W, H), 0), m))
        img.paste(box, (0, 0), box)
    return img


# ---------------------------------------------------------------- 手绘圆圈
def circle_mark(t, total, params=None):
    p = {"target": [720, 430, 480, 220], "color": DOT, "width": 6, "pad": 26}
    p.update(params or {})
    img, d = _canvas(p)
    tx, ty, tw, th = _tgt(p)
    pad = p["pad"]
    box = [tx - pad, ty - pad, tx + tw + pad, ty + th + pad]
    q = ease((t - 0.10) / 0.55)
    if q <= 0:
        return img
    # 两段弧错开画，像手画的一圈，末端稍微出头
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    rx, ry = (box[2] - box[0]) // 2, (box[3] - box[1]) // 2
    start = -100
    end = start + 380 * q
    d.arc([cx - rx, cy - ry, cx + rx, cy + ry], start, min(end, 250),
          fill=tuple(p["color"]) + (245,), width=p["width"])
    if end > 250:
        d.arc([cx - rx - 4, cy - ry + 3, cx + rx - 4, cy + ry + 3], 240, end,
              fill=tuple(p["color"]) + (245,), width=p["width"])
    return img


# ---------------------------------------------------------------- 聚光压暗
def spotlight_dim(t, total, params=None):
    p = {"target": [640, 380, 640, 300], "dark": 0.72, "radius": 22, "color": AMBER}
    p.update(params or {})
    img, d = _canvas(p)
    tx, ty, tw, th = _tgt(p)
    q = ease(t / 0.4)
    if q <= 0:
        return img
    alpha = int(255 * p["dark"] * q)
    veil = Image.new("RGBA", (W, H), (12, 10, 8, alpha))
    hole = Image.new("L", (W, H), 255)
    ImageDraw.Draw(hole).rounded_rectangle([tx, ty, tx + tw, ty + th],
                                           radius=p["radius"], fill=0)
    hole = hole.filter(ImageFilter.GaussianBlur(14))
    veil.putalpha(Image.composite(veil.getchannel("A"), Image.new("L", (W, H), 0), hole))
    img.paste(veil, (0, 0), veil)
    d.rounded_rectangle([tx, ty, tx + tw, ty + th], radius=p["radius"],
                        outline=tuple(p["color"]) + (int(200 * q),), width=3)
    return img


# ---------------------------------------------------------------- 箭头指向
def arrow_focus(t, total, params=None):
    p = {"target": [760, 460, 420, 200], "side": "bottom", "color": DOT, "width": 7}
    p.update(params or {})
    img, d = _canvas(p)
    tx, ty, tw, th = _tgt(p)
    ax, ay = tx + tw // 2, ty + th // 2
    if p["side"] == "bottom":
        sx, sy, ex, ey = ax, ty + th + 190, ax, ty + th + 18
    elif p["side"] == "top":
        sx, sy, ex, ey = ax, ty - 190, ax, ty - 18
    elif p["side"] == "left":
        sx, sy, ex, ey = tx - 220, ay, tx - 18, ay
    else:
        sx, sy, ex, ey = tx + tw + 220, ay, tx + tw + 18, ay
    q = ease(t / 0.4)
    if q <= 0:
        return img
    hx = sx + (ex - sx) * q
    hy = sy + (ey - sy) * q
    d.line([(sx, sy), (hx, hy)], fill=tuple(p["color"]) + (240,), width=p["width"])
    if q > 0.75:
        hs = int(24 * ease((q - 0.75) / 0.25))
        ang = math.atan2(ey - sy, ex - sx)
        for s in (+0.5, -0.5):
            d.line([(ex, ey), (ex - hs * math.cos(ang - s), ey - hs * math.sin(ang - s))],
                   fill=tuple(p["color"]) + (240,), width=p["width"])
    return img


# ---------------------------------------------------------------- 四角标框
def corner_brackets(t, total, params=None):
    p = {"target": [600, 340, 720, 400], "len": 56, "width": 6, "color": INK, "pad": 18}
    p.update(params or {})
    img, d = _canvas(p)
    tx, ty, tw, th = _tgt(p)
    pad = p["pad"]
    x0, y0, x1, y1 = tx - pad, ty - pad, tx + tw + pad, ty + th + pad
    q = ease(t / 0.42)
    if q <= 0:
        return img
    L = int(p["len"] * q)
    off = int((1 - q) * 40)
    x0, y0, x1, y1 = x0 - off, y0 - off, x1 + off, y1 + off
    c = tuple(p["color"]) + (240,)
    for (px, py, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(px, py), (px + sx * L, py)], fill=c, width=p["width"])
        d.line([(px, py), (px, py + sy * L)], fill=c, width=p["width"])
    return img


# ---------------------------------------------------------------- 序号徽章
def index_badge(t, total, params=None):
    p = {"target": [640, 400, 0, 0], "n": 1, "r": 54, "color": DOT, "size": 56}
    p.update(params or {})
    img, d = _canvas(p)
    tx, ty, _, _ = _tgt(p)
    q = ease((t - 0.05) / 0.32, "back")
    if q <= 0:
        return img
    r = int(p["r"] * q)
    d.ellipse([tx - r, ty - r, tx + r, ty + r], fill=tuple(p["color"]) + (250,))
    if r > p["r"] * 0.6:
        f = font(int(p["size"] * min(1, q)), bold=True)
        d.text((tx, ty), str(p["n"]), font=f, fill=(250, 246, 235, 255), anchor="mm")
    return img


# ---------------------------------------------------------------- 下划线扫过
def underline_sweep(t, total, params=None):
    p = {"target": [640, 520, 640, 0], "width": 10, "color": AMBER, "delay": 0.15}
    p.update(params or {})
    img, d = _canvas(p)
    tx, ty, tw, _ = _tgt(p)
    q = ease((t - p["delay"]) / 0.38)
    if q <= 0:
        return img
    d.line([(tx, ty), (tx + int(tw * q), ty)], fill=tuple(p["color"]) + (245,), width=p["width"])
    if q > 0.98:                                   # 收尾一个小顿点
        d.ellipse([tx + tw - 4, ty - 7, tx + tw + 10, ty + 7], fill=tuple(p["color"]) + (245,))
    return img
