"""数据类动效包：柱条 / 进度环 / 对比条 / 堆叠条 / 百分比环 / 排名 / 折线 /
指标卡 / 仪表盘 / 增减徽标

统一契约：render(t, total, params) -> PIL.Image(1920x1080, RGB)
- t 为「本镜内」秒数；所有动效在前 0.8-1.4 秒完成，之后保持
- params 全部可覆盖，见每个函数的默认字典
- 数据一律走 params，不许在模块里读文件或配置
- 数字动效必须用 ease() 缓动，不许线性跳字；基准帧建议 at=total*0.7
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from _core import (AMBER, DOT, H, INK, MUTE, PALE, W, ease, font, lerp, paper,
                   shadow, text_w)

BLUE = (58, 92, 120)
GREEN = (74, 112, 86)
GOLD = (196, 150, 58)
PALETTE = [AMBER, BLUE, GREEN, GOLD, DOT]


def _base(p):
    img = paper(tuple(p.get("bg", (241, 235, 216))))
    return img, ImageDraw.Draw(img)


def _title(d, p, sub=None):
    f = font(52, bold=True)
    d.text((W // 2, 138), p.get("title", ""), font=f, fill=INK, anchor="mm")
    if sub:
        d.text((W // 2, 206), sub, font=font(30), fill=MUTE, anchor="mm")


def _paste(img, layer):
    """RGB 画布上安全叠加 RGBA 图层。"""
    if img.mode == "RGBA":
        img.alpha_composite(layer)
    else:
        img.paste(layer, (0, 0), layer)


# ---------------------------------------------------------------- 1 柱条生长
def bar_grow(t, total, params=None):
    p = {"title": "一遍出片，各环节耗时", "labels": ["采访", "提示词", "生成"],
         "values": [22, 58, 92], "unit": "%", "max": 100, "bar_w": 220,
         "baseline_y": 830, "top": 340, "stagger": 0.14, "dur": 0.72}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    n = len(p["values"])
    span = 1420
    step = span // max(1, n)
    x0 = (W - span) // 2
    by = int(p["baseline_y"])
    d.line([(x0 - 40, by + 6), (x0 + span + 40, by + 6)], fill=MUTE, width=3)
    for i, v in enumerate(p["values"]):
        q = ease((t - i * p["stagger"]) / p["dur"])
        if q <= 0:
            continue
        bx = x0 + i * step + (step - int(p["bar_w"])) // 2
        ratio = max(0.0, min(1.0, float(v) / float(p["max"] or 1)))
        h = int((by - int(p["top"])) * ratio * q)
        col = PALETTE[i % len(PALETTE)]
        d.rounded_rectangle([bx, by - h, bx + int(p["bar_w"]), by], radius=14, fill=col)
        # 顶端数值随柱一起长，避免数字先到、柱子后到
        val = int(float(v) * q)
        f = font(54, bold=True)
        d.text((bx + int(p["bar_w"]) // 2, by - h - 46), f"{val}{p['unit']}",
               font=f, fill=INK, anchor="mm")
        d.text((bx + int(p["bar_w"]) // 2, by + 62), str(p["labels"][i]),
               font=font(40), fill=MUTE, anchor="mm")
    return img


# ---------------------------------------------------------------- 2 进度环
def progress_ring(t, total, params=None):
    p = {"title": "提示词完成度", "value": 78, "label": "已覆盖的镜头信息",
         "dur": 1.0, "ring": 34, "r": 270, "color": AMBER, "unit": "%"}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    cx, cy, r = W // 2, 570, int(p["r"])
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, 0, 360, fill=(214, 206, 186), width=int(p["ring"]))
    q = ease(t / p["dur"])
    d.arc(box, -90, -90 + 360 * q, fill=tuple(p["color"]), width=int(p["ring"]))
    f = font(150, bold=True)
    d.text((cx, cy - 10), f"{int(float(p['value']) * q)}{p['unit']}",
           font=f, fill=INK, anchor="mm")
    d.text((cx, cy + 118), p["label"], font=font(38), fill=MUTE, anchor="mm")
    return img


# ---------------------------------------------------------------- 3 对比双条
def compare_bars(t, total, params=None):
    p = {"title": "同一句话，差了多少", "left": ["只给一句话", 30],
         "right": ["说清要求", 92], "max": 100, "unit": "分",
         "y": [450, 680], "dur": 0.7, "gap": 0.16}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    x0, full = 300, 1320
    rows = [(p["left"], 0, MUTE), (p["right"], 1, AMBER)]
    for (label, val), i, col in rows:
        q = ease((t - i * p["gap"]) / p["dur"])
        y = int(p["y"][i])
        d.text((x0, y - 66), label, font=font(50, bold=True), fill=INK, anchor="la")
        d.rounded_rectangle([x0, y, x0 + full, y + 96], radius=22, fill=(222, 214, 194))
        w = int(full * max(0.0, min(1.0, float(val) / float(p["max"] or 1))) * q)
        if w > 4:
            d.rounded_rectangle([x0, y, x0 + w, y + 96], radius=22, fill=col)
        d.text((x0 + full - 16, y + 48), f"{int(float(val) * q)}{p['unit']}",
               font=font(54, bold=True), fill=INK if i == 0 else col, anchor="rm")
    return img


# ---------------------------------------------------------------- 4 堆叠条
def stacked_bar(t, total, params=None):
    p = {"title": "一份提示词里都有什么", "parts": [("采访", 25), ("分镜", 40), ("光线与机位", 35)],
         "x0": 240, "x1": 1680, "y": 520, "h": 150, "dur": 0.55, "stagger": 0.22}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    vals = [float(v) for _, v in p["parts"]]
    s = sum(vals) or 1
    x0, x1 = int(p["x0"]), int(p["x1"])
    cur = x0
    for i, (label, v) in enumerate(p["parts"]):
        q = ease((t - i * p["stagger"]) / p["dur"])
        seg = (x1 - x0) * float(v) / s
        if q <= 0:
            cur += seg
            continue
        w = int(seg * q)
        col = PALETTE[i % len(PALETTE)]
        d.rectangle([cur, int(p["y"]), cur + w, int(p["y"]) + int(p["h"])], fill=col)
        if w > 150:
            d.text((cur + w // 2, int(p["y"]) + int(p["h"]) // 2), label,
                   font=font(38, bold=True), fill=PALE, anchor="mm")
            d.text((cur + w // 2, int(p["y"]) + int(p["h"]) + 52), f"{int(float(v) * q)}%",
                   font=font(34), fill=INK, anchor="mm")
        cur += seg
    return img


# ---------------------------------------------------------------- 5 百分比环
def percent_donut(t, total, params=None):
    p = {"title": "最容易被漏掉的信息", "slices": [("机位", 35), ("光线", 40), ("节奏", 25)],
         "cx": 760, "cy": 590, "r": 290, "hole": 150, "dur": 0.9, "stagger": 0.16}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    cx, cy, r = int(p["cx"]), int(p["cy"]), int(p["r"])
    box = [cx - r, cy - r, cx + r, cy + r]
    vals = [float(v) for _, v in p["slices"]]
    s = sum(vals) or 1
    ang = -90.0
    for i, (label, v) in enumerate(p["slices"]):
        sweep = 360.0 * float(v) / s
        q = ease((t - i * p["stagger"]) / p["dur"])
        if q > 0:
            col = PALETTE[i % len(PALETTE)]
            d.pieslice(box, ang, ang + sweep * q, fill=col)
            mid = math.radians(ang + sweep / 2)
            tx = cx + int((r * 0.72) * math.cos(mid))
            ty = cy + int((r * 0.72) * math.sin(mid))
            d.text((tx, ty), f"{int(float(v))}%", font=font(40, bold=True),
                   fill=PALE, anchor="mm")
        ang += sweep
    d.ellipse([cx - int(p["hole"]), cy - int(p["hole"]),
               cx + int(p["hole"]), cy + int(p["hole"])], fill=tuple(p.get("bg", (241, 235, 216))))
    d.text((cx, cy), "全片", font=font(52, bold=True), fill=INK, anchor="mm")
    for i, (label, v) in enumerate(p["slices"]):
        y = 380 + i * 96
        d.rounded_rectangle([1330, y, 1374, y + 44], radius=8, fill=PALETTE[i % len(PALETTE)])
        d.text((1400, y + 22), f"{label}  {int(v)}%", font=font(40), fill=INK, anchor="lm")
    return img


# ---------------------------------------------------------------- 6 排名变化
def rank_shift(t, total, params=None):
    p = {"title": "AI 猜错的顺序，被重新排好", "rows": ["机位", "光线", "表情", "节奏"],
         "order_to": [2, 0, 3, 1], "x0": 460, "y0": 350, "row_h": 150,
         "dur": 0.9, "stagger": 0.10}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    rows = p["rows"]
    to = list(p["order_to"]) + list(range(len(rows)))
    to = to[:len(rows)]
    y0, rh = int(p["y0"]), int(p["row_h"])
    x0, bw = int(p["x0"]), 1000
    for i, name in enumerate(rows):
        q = ease((t - i * p["stagger"]) / p["dur"])
        y = int(lerp(y0 + i * rh, y0 + to[i] * rh, q))
        col = AMBER if i == 0 else INK
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle([x0, y, x0 + bw, y + 108], radius=18,
                             fill=(250, 246, 235, 255), outline=(190, 180, 158, 255), width=2)
        ld.ellipse([x0 + 28, y + 22, x0 + 92, y + 86], fill=tuple(col) + (255,))
        ld.text((x0 + 60, y + 54), str(to[i] + 1), font=font(36, bold=True),
                fill=(250, 246, 235, 255), anchor="mm")
        ld.text((x0 + 130, y + 54), name, font=font(50, bold=True),
                fill=tuple(INK) + (255,), anchor="lm")
        _paste(img, lay)
    return img


# ---------------------------------------------------------------- 7 折线爬升
def line_chart(t, total, params=None):
    p = {"title": "改到第几轮，画面才稳定", "points": [12, 26, 22, 55, 48, 90],
         "labels": ["1", "2", "3", "4", "5", "6"], "x0": 300, "x1": 1620,
         "y_top": 350, "y_bottom": 830, "max": 100, "dur": 0.85, "color": AMBER}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    x0, x1 = int(p["x0"]), int(p["x1"])
    yt, yb = int(p["y_top"]), int(p["y_bottom"])
    for k in range(5):
        y = yt + int((yb - yt) * k / 4)
        d.line([(x0, y), (x1, y)], fill=(214, 206, 186), width=2)
    pts = []
    n = len(p["points"])
    for i, v in enumerate(p["points"]):
        x = x0 + int((x1 - x0) * i / max(1, n - 1))
        y = yb - int((yb - yt) * max(0.0, min(1.0, float(v) / float(p["max"] or 1))))
        pts.append((x, y))
        d.text((x, yb + 42), str(p["labels"][i]), font=font(32), fill=MUTE, anchor="mm")
    seg = (p["dur"] / max(1, n - 1))
    for i in range(n - 1):
        q = ease((t - i * seg) / seg)
        if q <= 0:
            continue
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        d.line([(ax, ay), (int(lerp(ax, bx, q)), int(lerp(ay, by, q)))],
               fill=tuple(p["color"]), width=7)
    for i, (x, y) in enumerate(pts):
        q = ease((t - i * seg) / 0.18)
        if q > 0:
            r = int(11 * q)
            d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(p["color"]))
    return img


# ---------------------------------------------------------------- 8 指标卡
def metric_cards(t, total, params=None):
    p = {"title": "一次生成，得到什么", "cards": [("3", "个镜头"), ("1280", "字提示词"), ("1", "遍出片")],
         "y": 420, "w": 420, "h": 360, "gap": 60, "dur": 0.48, "stagger": 0.17}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    cards = p["cards"]
    w, h, gap = int(p["w"]), int(p["h"]), int(p["gap"])
    x0 = (W - (len(cards) * w + (len(cards) - 1) * gap)) // 2
    for i, (num, label) in enumerate(cards):
        q = ease((t - i * p["stagger"]) / p["dur"], "back")
        x = x0 + i * (w + gap)
        y = int(p["y"]) + int((1 - min(1.0, max(0.0, q))) * 90)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle([x, y, x + w, y + h], radius=26,
                             fill=(250, 246, 235, 255), outline=(190, 180, 158, 255), width=3)
        ld.rectangle([x + 46, y + 44, x + 116, y + 52], fill=tuple(PALETTE[i % len(PALETTE)]) + (255,))
        ld.text((x + w // 2, y + 190), str(num), font=font(112, bold=True),
                fill=tuple(INK) + (255,), anchor="mm")
        ld.text((x + w // 2, y + 290), label, font=font(42),
                fill=tuple(MUTE) + (255,), anchor="mm")
        _paste(img, lay)
    return img


# ---------------------------------------------------------------- 9 仪表盘
def gauge_meter(t, total, params=None):
    p = {"title": "画面稳定度", "value": 82, "label": "首帧对齐之后",
         "cx": 960, "cy": 760, "r": 380, "width": 40, "dur": 1.0, "unit": ""}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    cx, cy, r = int(p["cx"]), int(p["cy"]), int(p["r"])
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, 180, 360, fill=(214, 206, 186), width=int(p["width"]))
    q = ease(t / p["dur"])
    frac = max(0.0, min(1.0, float(p["value"]) / 100.0)) * q
    d.arc(box, 180, 180 + 180 * frac, fill=AMBER, width=int(p["width"]))
    ang = math.radians(180 + 180 * frac)
    ex, ey = cx + int(r * 0.82 * math.cos(ang)), cy + int(r * 0.82 * math.sin(ang))
    d.line([(cx, cy), (ex, ey)], fill=INK, width=12)
    d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=INK)
    d.text((cx, cy - 150), f"{int(float(p['value']) * q)}{p['unit']}",
           font=font(120, bold=True), fill=INK, anchor="mm")
    d.text((cx, cy + 96), p["label"], font=font(38), fill=MUTE, anchor="mm")
    return img


# ---------------------------------------------------------------- 10 增减徽标
def delta_badge(t, total, params=None):
    p = {"title": "生成效率", "before": 1, "after": 3, "unit": "倍",
         "note": "从反复重来，到一遍出片", "y": 560, "dur": 0.9, "delay": 0.12}
    p.update(params or {})
    img, d = _base(p)
    _title(d, p)
    q = ease((t - p["delay"]) / p["dur"])
    y = int(p["y"])
    f = font(180, bold=True)
    d.text((W // 2 - 250, y), str(p["before"]), font=f, fill=MUTE, anchor="mm")
    d.text((W // 2, y), "→", font=font(120), fill=MUTE, anchor="mm")
    d.text((W // 2 + 260, y), f"{p['after']}{p['unit']}", font=f, fill=AMBER, anchor="mm")
    # 增幅徽章带轻微回弹
    qb = ease((t - p["delay"] - 0.34) / 0.38, "back")
    if qb > 0:
        delta = float(p["after"]) - float(p["before"])
        txt = f"+{delta:g}{p['unit']}"
        fb = font(52, bold=True)
        bw = text_w(d, txt, fb) + 80
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        x = W // 2 + 250 - bw // 2
        ld.rounded_rectangle([x, y + 110, x + bw, y + 208], radius=49,
                             fill=tuple(DOT) + (int(255 * min(1.0, qb)),))
        ld.text((W // 2 + 250, y + 159), txt, font=fb,
                fill=(250, 246, 235, int(255 * min(1.0, qb))), anchor="mm")
        _paste(img, lay)
    d.text((W // 2, y + 290), p["note"], font=font(42), fill=MUTE, anchor="mm")
    return img


ALL = ["bar_grow", "progress_ring", "compare_bars", "stacked_bar", "percent_donut",
       "rank_shift", "line_chart", "metric_cards", "gauge_meter", "delta_badge"]
