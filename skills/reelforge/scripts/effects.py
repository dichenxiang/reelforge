#!/usr/bin/env python
"""效果库 CLI —— 跨片子、跨 agent 复用的动效仓库。

位置默认 ~/.reelforge/effects，可用 REELFORGE_EFFECTS 覆盖。
仓库结构：
    index.json            清单（含绝对路径，换 agent 也能定位）
    fx/<id>.py            效果模块，必须暴露 render(t, total, params) -> PIL.Image
    baselines/<id>.png    基准帧（回归对比用）
    previews/<id>.png     最近一次预览

用法：
    python effects.py init
    python effects.py where
    python effects.py new frame_zoom --title "屏幕边框+放大条" --tags zoom,screen
    python effects.py register ./my_fx.py --id mascot --title "吉祥物气泡" --tags mascot
    python effects.py list [--tag zoom]
    python effects.py path frame_zoom
    python effects.py check
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

TEMPLATE = '''"""效果：{title}

契约：render(t, total, params) -> PIL.Image（1920×1080, RGB）
- t        当前时间（秒）
- total    该镜头总时长（秒）
- params   参数字典，见 DEFAULT_PARAMS
禁止在模块内读外部状态；所有可变项走 params。
"""
from __future__ import annotations

from PIL import Image, ImageDraw

DEFAULT_PARAMS = {{
    "bg": [241, 235, 216],
    "fg": [26, 22, 16],
}}


def render(t: float, total: float, params: dict | None = None) -> Image.Image:
    p = dict(DEFAULT_PARAMS)
    p.update(params or {{}})
    p_t = max(0.0, min(1.0, t / max(total, 0.01)))

    img = Image.new("RGB", (1920, 1080), tuple(p["bg"]))
    d = ImageDraw.Draw(img)
    # TODO: 在这里写效果；建议先把 p_t 映射成 0-1 的缓动量
    d.text((120, 500), "{eid}", fill=tuple(p["fg"]))
    return img
'''


def root() -> Path:
    return Path(os.environ.get("REELFORGE_EFFECTS") or (Path.home() / ".reelforge" / "effects"))


def index_path() -> Path:
    return root() / "index.json"


def load() -> dict:
    if not index_path().exists():
        return {"version": 1, "updated_at": None, "root": str(root().resolve()), "items": []}
    return json.loads(index_path().read_text(encoding="utf-8"))


def save(idx: dict) -> None:
    idx["root"] = str(root().resolve())
    idx["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    index_path().write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def ensure() -> None:
    for sub in ("fx", "baselines", "previews"):
        (root() / sub).mkdir(parents=True, exist_ok=True)


def _card(eid: str, a) -> dict:
    """配方卡：id / 意图 / 能量 / 输入 / 参数 / 已知坑 / 入口 / 基准帧。"""
    return {
        "id": eid,
        "title": getattr(a, "title", "") or eid,
        "desc": getattr(a, "desc", "") or "",
        "intent": getattr(a, "intent", "") or "",
        "energy": getattr(a, "energy", "") or "中",
        "inputs": [t.strip() for t in (getattr(a, "inputs", "") or "").split(",") if t.strip()],
        "pitfalls": [t.strip() for t in (getattr(a, "pitfalls", "") or "").split("|") if t.strip()],
        "params": getattr(a, "params", "") or "",
        "tags": [t.strip() for t in (getattr(a, "tags", "") or "").split(",") if t.strip()],
        "entry": f"fx/{eid}.py",
        "baseline": None,
        "preview": None,
        "used_in": [],
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def cmd_init(_a) -> int:
    ensure()
    idx = load()
    save(idx)
    print(f"效果库就绪：{root().resolve()}")
    print(f"  条目 {len(idx['items'])} 个")
    print(f"  环境变量 REELFORGE_EFFECTS 可改位置（当前：{'已设置' if os.environ.get('REELFORGE_EFFECTS') else '未设置，用默认'}）")
    return 0


def cmd_where(_a) -> int:
    print(str(root().resolve()))
    print(f"  index.json {'存在' if index_path().exists() else '缺失（先跑 init）'}")
    return 0


def cmd_new(a) -> int:
    ensure()
    idx = load()
    if any(x["id"] == a.id for x in idx["items"]):
        print(f"已存在：{a.id}", file=sys.stderr)
        return 1
    f = root() / "fx" / f"{a.id}.py"
    f.write_text(TEMPLATE.format(title=a.title or a.id, eid=a.id), encoding="utf-8")
    idx["items"].append(_card(a.id, a))
    save(idx)
    print(f"已创建 {f}")
    print("  下一步：写好 render()，然后 `python effects.py baseline {}`".format(a.id))
    return 0


def cmd_register(a) -> int:
    ensure()
    src = Path(a.file).resolve()
    if not src.exists():
        print(f"找不到 {src}", file=sys.stderr)
        return 1
    idx = load()
    eid = a.id or src.stem
    idx["items"] = [x for x in idx["items"] if x["id"] != eid]
    dst = root() / "fx" / f"{eid}.py"
    shutil.copy2(src, dst)
    idx["items"].append(_card(eid, a))
    save(idx)
    print(f"已登记 {eid} → {dst}")
    return 0


def cmd_list(a) -> int:
    idx = load()
    items = idx["items"]
    if a.tag:
        items = [x for x in items if a.tag in x.get("tags", [])]
    if not items:
        print("（空）先 `python effects.py init` 再 `new` / `register`")
        return 0
    for x in items:
        state = "待抽取" if x.get("status") == "pending" else (x.get("baseline") or "无基准帧")
        print(f"{x['id']:18s} {x['title']:24s} {','.join(x.get('tags', [])) or '-':22s} {state}")
    print(f"\n共 {len(items)} 个 · 库位置 {root().resolve()}")
    return 0


def cmd_card(a) -> int:
    idx = load()
    hit = next((x for x in idx["items"] if x["id"] == a.id), None)
    if not hit:
        print(f"未登记：{a.id}", file=sys.stderr)
        return 1
    print(f"## {hit['id']} — {hit.get('title','')}")
    if hit.get("intent"):
        print(f"何时用：{hit['intent']}")
    print(f"能量：{hit.get('energy','-')}   输入：{','.join(hit.get('inputs') or []) or '-'}")
    if hit.get("desc"):
        print(f"说明：{hit['desc']}")
    if hit.get("params"):
        print(f"参数：{hit['params']}")
    for pf in (hit.get("pitfalls") or []):
        print(f"  坑：{pf}")
    if hit.get("entry"):
        print(f"入口：{hit['entry']}")
    if hit.get("baseline"):
        print(f"基准帧：{hit['baseline']}")
    return 0


def cmd_path(a) -> int:
    idx = load()
    hit = next((x for x in idx["items"] if x["id"] == a.id), None)
    if not hit:
        print(f"未登记：{a.id}", file=sys.stderr)
        return 1
    print(str((root() / hit["entry"]).resolve()))
    return 0


def cmd_check(_a) -> int:
    idx = load()
    runnable = [x for x in idx["items"] if x.get("entry")]
    missing = [x["id"] for x in runnable if not (root() / x["entry"]).exists()]
    nobase = [x["id"] for x in runnable if not x.get("baseline")]
    pending = [x["id"] for x in idx["items"] if x.get("status") == "pending"]
    for i in missing:
        print(f"文件缺失：{i}")
    for i in nobase:
        print(f"缺基准帧：{i}（跑 `python effects.py baseline {i}`）")
    if pending:
        print(f"待抽取：{len(pending)} 个（{', '.join(pending)}）")
    if not missing and not nobase:
        print(f"OK：可运行效果 {len(runnable)} 个齐全")
    return 1 if missing else 0


def cmd_baseline(a) -> int:
    """渲染一帧存为基准图，后续改动可对比。"""
    import importlib.util
    idx = load()
    hit = next((x for x in idx["items"] if x["id"] == a.id), None)
    if not hit:
        print(f"未登记：{a.id}", file=sys.stderr)
        return 1
    f = root() / hit["entry"]
    spec = importlib.util.spec_from_file_location(f"fx_{a.id}", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    total = a.total
    extra = json.loads(a.params) if a.params else {}
    img = mod.render(a.at if a.at is not None else total * 0.6, total, extra)
    out = root() / "baselines" / f"{a.id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    hit["baseline"] = f"baselines/{a.id}.png"
    save(idx)
    print(f"基准帧已存 {out}")
    return 0


# ---------------------------------------------------------------- 卡片目录与匹配

BEAT_RULES = [
    ("设问", ["？", "?", "为什么", "怎么", "是不是", "难道", "凭什么"]),
    ("数据", ["%", "百分之", "倍", "万", "亿", "千人", "增长", "下降", "一半", "三成"]),
    ("对比", ["但是", "而是", "相反", "不如", "反而", "对比", "相比", " vs "]),
    ("步骤", ["第一步", "第二步", "首先", "然后", "接着", "最后再", "先", "再"]),
    ("列举", ["第一", "第二", "第三", "其次", "还有", "另外", "以及", "、"]),
    ("转折", ["但", "然而", "其实", "不过", "问题是", "可是"]),
    ("定义", ["所谓", "指的是", "意思是", "就是说"]),
    ("例证", ["比如", "例如", "举个例子", "像是", "就像", "拿"]),
    ("机制", ["因为", "所以", "导致", "就会", "才能", "是因为", "原理"]),
    ("过程演示", ["打开", "点击", "输入", "发送", "回到", "进入", "装好"]),
    ("强调", ["注意", "重点", "关键", "一定要", "记住", "核心"]),
    ("号召", ["关注", "点赞", "订阅", "评论区", "主页", "转发", "收藏"]),
]


def _catalog():
    """先读本地库，再读 skill 自带的 catalog（换机器也能用）。"""
    vocab, cards = {"beats": [], "inputs": {}}, []
    seen = set()
    dirs = []
    local = root() / "catalog"
    if local.exists():
        dirs.append(local)
    bundled = Path(__file__).resolve().parent.parent / "catalog"
    if bundled.exists() and bundled.resolve() != local.resolve():
        dirs.append(bundled)
    for d in dirs:
        if (d / "vocab.json").exists() and not vocab["beats"]:
            vocab = json.loads((d / "vocab.json").read_text(encoding="utf-8"))
        for f in sorted(d.glob("*.json")):
            if f.name == "vocab.json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for c in (data.get("cards") or []):
                key = (c.get("source"), c.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                cards.append(c)
    return vocab, cards


def _split_beats(text: str):
    import re
    raw = [x.strip() for x in re.split(r"(?<=[。！？!?])", text) if x.strip()]
    merged = []
    for seg in raw:
        if merged and len(seg) <= 6:          # 「机位？」这类碎片并回上一拍
            merged[-1] += seg
        else:
            merged.append(seg)
    raw = merged
    out = []
    for i, s in enumerate(raw):
        hits = []
        for name, kws in BEAT_RULES:
            got = [k for k in kws if k in s]
            if got:
                hits.append(name)
        if (s.count("这样") >= 2 or s.count("、") >= 2) and "列举" not in hits:
            hits.append("列举")
        if not hits:
            hits = ["论点"]
        if i == 0:
            hits = ["钩子"] + [h for h in hits if h != "钩子"]
        if len(s) <= 12 and "论点" in hits:
            hits.append("金句")
        seen, uniq = set(), []
        for h in hits:
            if h not in seen:
                seen.add(h)
                uniq.append(h)
        out.append({"i": i + 1, "text": s, "beat": uniq[0], "beats": uniq})
    return out


def _kws(text: str) -> set:
    import re
    grams = set()
    for run in re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{3,}", text or ""):
        if run.isascii():
            grams.add(run.lower())
            continue
        for i in range(len(run) - 1):
            grams.add(run[i:i + 2])
    return grams


def _score(card, beat, have_inputs, energy, beat_kw=None, beat_list=None):
    sc = 0.0
    cb = set(card.get("beats") or [])
    if beat_list and cb & set(beat_list):
        sc += 3
    if beat_kw:
        ck = _kws(f"{card.get('title','')} {card.get('intent','')} {' '.join(card.get('beats') or [])}")
        inter = len(beat_kw & ck)
        sc += 2.5 * min(1.0, inter / 6.0)
    ci = set(card.get("inputs") or []) - {"场"}
    if ci:
        inter = len(ci & have_inputs)
        sc += 2.0 * inter / len(ci)
    if energy and card.get("energy") == energy:
        sc += 1
    if (card.get("priority") or "P2") in ("P0", "P1"):
        sc += 0.5
    return sc


def cmd_catalog(a) -> int:
    _v, cards = _catalog()
    rows = cards
    if a.source:
        rows = [c for c in rows if c.get("source") == a.source]
    if a.category:
        rows = [c for c in rows if c.get("category") == a.category]
    if a.beat:
        rows = [c for c in rows if a.beat in (c.get("beats") or [])]
    if a.grep:
        kw = a.grep.lower()
        rows = [c for c in rows if kw in (c.get("title", "") + c.get("intent", "")).lower()]
    for c in rows[: a.limit]:
        beats = "/".join(c.get("beats") or []) or "-"
        print(f"{c['source']:10s} {c['id'][:28]:28s} {c['title'][:14]:14s} {c.get('category','')[:8]:8s} {c.get('energy',''):1s} {beats}")
    print(f"\n共 {len(rows)} 条（全部 {len(cards)}）")
    return 0


def cmd_beats(a) -> int:
    text = Path(a.script).read_text(encoding="utf-8")
    beats = _split_beats(text)
    for b in beats:
        print(f"{b['i']:2d}  {b['beat']:3s}  {b['text'][:42]}")
    from collections import Counter
    print("\n节拍分布:", dict(Counter(b["beat"] for b in beats)))
    return 0


def cmd_suggest(a) -> int:
    text = Path(a.script).read_text(encoding="utf-8")
    have = {t.strip() for t in (a.inputs or "").split(",") if t.strip()} | {"文"}
    _vocab, cards = _catalog()
    if not cards:
        print("卡片目录为空：先把索引放到 ~/.reelforge/effects/catalog/", file=sys.stderr)
        return 1
    used, used_cat = set(), {}
    for b in _split_beats(text):
        bkw = _kws(b["text"])
        bl = b.get("beats") or [b["beat"]]
        ranked = sorted(cards, key=lambda c: -_score(c, b["beat"], have, a.energy, bkw, bl))
        cand = [c for c in ranked if _score(c, b["beat"], have, a.energy, bkw, bl) >= 2.6]
        cand = [c for c in cand if c["id"] not in used
                and used_cat.get(c["category"], 0) < 2]
        picks = cand[: a.top]
        if not picks:
            print(f"\n[{b['i']:02d}] {'+'.join(bl)}｜{b['text'][:30]}")
            print("     （无高置信匹配 → 用基础字幕/素材呈现，别硬套卡）")
            continue
        print(f"\n[{b['i']:02d}] {'+'.join(bl)}｜{b['text'][:30]}")
        for k, c in enumerate(picks):
            star = "★" if k == 0 else " "
            print(f"  {star} {c['category']}·{c['title']}（{'/'.join(c.get('beats') or []) or '通用'}｜能量{c.get('energy')}）")
            print(f"     {c['intent'][:70]}")
        used.add(picks[0]["id"])
        used_cat[picks[0]["category"]] = used_cat.get(picks[0]["category"], 0) + 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ReelForge 效果库")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("where").set_defaults(fn=cmd_where)
    sub.add_parser("check").set_defaults(fn=cmd_check)

    p = sub.add_parser("new")
    p.add_argument("id")
    p.add_argument("--title", default="")
    p.add_argument("--desc", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--intent", default="")
    p.add_argument("--energy", default="中")
    p.add_argument("--inputs", default="")
    p.add_argument("--pitfalls", default="", help="多条用 | 分隔")
    p.add_argument("--params", default="")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("register")
    p.add_argument("file")
    p.add_argument("--id", default="")
    p.add_argument("--title", default="")
    p.add_argument("--desc", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--intent", default="")
    p.add_argument("--energy", default="中")
    p.add_argument("--inputs", default="")
    p.add_argument("--pitfalls", default="", help="多条用 | 分隔")
    p.add_argument("--params", default="")
    p.set_defaults(fn=cmd_register)

    p = sub.add_parser("list")
    p.add_argument("--tag", default="")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("baseline")
    p.add_argument("id")
    p.add_argument("--at", type=float, default=None)
    p.add_argument("--total", type=float, default=4.0)
    p.add_argument("--params", default="")
    p.set_defaults(fn=cmd_baseline)

    p = sub.add_parser("catalog")
    p.add_argument("--source", default="")
    p.add_argument("--category", default="")
    p.add_argument("--beat", default="")
    p.add_argument("--grep", default="")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(fn=cmd_catalog)

    p = sub.add_parser("beats")
    p.add_argument("--script", required=True)
    p.set_defaults(fn=cmd_beats)

    p = sub.add_parser("suggest")
    p.add_argument("--script", required=True)
    p.add_argument("--inputs", default="", help="可用的素材类型：图,截图,V,人")
    p.add_argument("--energy", default="")
    p.add_argument("--top", type=int, default=3)
    p.set_defaults(fn=cmd_suggest)

    p = sub.add_parser("card")
    p.add_argument("id")
    p.set_defaults(fn=cmd_card)

    p = sub.add_parser("path")
    p.add_argument("id")
    p.set_defaults(fn=cmd_path)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
