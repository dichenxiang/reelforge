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
