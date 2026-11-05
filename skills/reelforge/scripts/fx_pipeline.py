#!/usr/bin/env python
"""稿子 → 镜头表 → 片段：把效果库真正接进流水线。

不再靠人描述动效：给一段口播稿，自动切句、判节拍、从效果库里挑可运行
效果、按配方卡填参数，产出可直接渲染的 shots.json；再一键渲成 mp4 片段，
或直接 emit 成项目 make.py 能吃的 shots 列表。

    python fx_pipeline.py check
    python fx_pipeline.py plan --script 稿子.txt --out shots.json [--image 截图.png]
    python fx_pipeline.py plan --script 稿子.txt --out shots.json --with-transitions --a a.mp4 --b b.mp4
    python fx_pipeline.py render --shots shots.json --out-dir out/ [--limit 4]
    python fx_pipeline.py preview --fx bar_grow --at 1.2 --out preview.png
    python fx_pipeline.py emit --shots shots.json     # 打印可粘进 make.py 的代码

镜头表契约（项目侧）：
    shots = [("fx", {"fx": "bar_grow", "params": {"values": [20, 60, 90]}}, None, None, None, 1.0)]
或最简：
    shots = [("fx", "char_rise", {"text": "一句话"}, None, None, 1.0)]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "effects"))
import runtime                                             # noqa: E402
import effects as fxlib                                    # noqa: E402

TRANS_CYCLE = ["push_slide", "wipe_bar", "ink_spread", "blinds", "flash_white",
               "zoom_through", "card_flip", "fade_dip", "shake_cut"]

DATA_FX = {"bar_grow", "progress_ring", "compare_bars", "stacked_bar", "percent_donut",
           "rank_shift", "line_chart", "metric_cards", "gauge_meter", "delta_badge",
           "count_up"}

# 按语义节拍先圈定候选，再打分。纯关键词打分会把「设问」配到堆叠条这种
# 明显不对的效果上，所以必须先有语义白名单。
BEAT_POOL = {
    "钩子": ["char_rise", "double_block_lines", "metric_cards", "blur_focus_in"],
    "设问": ["blur_focus_in", "circle_mark", "callout_line", "char_rise", "corner_brackets"],
    "数据": ["bar_grow", "progress_ring", "compare_bars", "delta_badge", "count_up",
             "marker_highlight", "line_chart", "metric_cards"],
    "对比": ["double_block_lines", "compare_bars", "rank_shift", "delta_badge", "spotlight_dim"],
    "列举": ["metric_cards", "stacked_bar", "percent_donut", "index_badge", "bar_grow"],
    "步骤": ["index_badge", "arrow_focus", "rank_shift", "metric_cards"],
    "转折": ["double_block_lines", "compare_bars", "stamp_slam", "underline_sweep"],
    "强调": ["marker_highlight", "circle_mark", "callout_line", "underline_sweep",
             "spotlight_dim", "corner_brackets"],
    "金句": ["stamp_slam", "underline_sweep", "char_rise", "blur_focus_in", "marker_highlight"],
    "号召": ["stamp_slam", "marker_highlight", "underline_sweep"],
    "论点": ["char_rise", "blur_focus_in", "double_block_lines", "marker_highlight"],
    "过程演示": ["metric_cards", "bar_grow", "line_chart", "index_badge"],
    "机制": ["line_chart", "rank_shift", "arrow_focus", "stacked_bar"],
    "例证": ["callout_line", "circle_mark", "spotlight_dim", "corner_brackets"],
    "定义": ["percent_donut", "double_block_lines", "corner_brackets"],
}

FALLBACK = ["char_rise", "blur_focus_in", "marker_highlight", "underline_sweep",
            "double_block_lines", "circle_mark"]


# ------------------------------------------------------------------ 参数自动填充
def _words(sent: str):
    parts = [x.strip() for x in re.split(r"[、,，和以及与/]", sent) if x.strip()]
    parts = [x for x in parts if 1 < len(x) <= 10]
    return parts if len(parts) >= 2 else None


def _pair(sent: str):
    m = re.split(r"不是(.+?)[，,](?:而是|是)(.+?)[。！？]?$", sent)
    if len(m) >= 3:
        return ["不是" + m[1], "而是" + m[2]]
    for sep in ("相比", "对比", "，", ","):
        if sep in sent:
            cut = sent.find(sep)
            left, right = sent[:cut].strip(), sent[cut:].strip("，, ")
            if left and right:
                return [left, right]
    return None


def _context(sent: str, args) -> dict:
    nums = [float(x) if "." in x else int(x)
            for x in re.findall(r"\d+(?:\.\d+)?", sent)]
    clean = sent.rstrip("。！？!?，, ")
    return {
        "sentence": clean,
        "short": clean[:12].rstrip("，,、 "),
        "value": max(nums) if nums else None,   # 「从 120 涨到 1280」该滚到 1280，不是 120
        "numbers": nums if len(nums) >= 2 else None,
        "labels": _words(clean),
        "pair": _pair(clean),
        "image": getattr(args, "image", None),
        "target": getattr(args, "target", None),
        "focus": getattr(args, "focus", None),
    }


def _fill(auto: dict, sent: str, args) -> dict:
    ctx = _context(sent, args)
    out = {}
    for key, tpl in (auto or {}).items():
        if not isinstance(tpl, str):
            out[key] = tpl
            continue
        m = re.fullmatch(r"\{(\w+)\??\}", tpl.strip())
        if not m:
            out[key] = tpl
            continue
        val = ctx.get(m.group(1))
        if val is None or val == "" or val == []:
            continue            # 抽不到就用效果自带默认，绝不塞空值
        out[key] = val
    return out


# ------------------------------------------------------------------ 选效果
def _score(card: dict, beat: dict, used: dict, energy: str) -> float:
    cbeats = set(card.get("beats") or [])
    sc = 0.0
    if beat["beat"] in cbeats:
        sc += 3.0
    if set(beat.get("beats") or []) & cbeats:
        sc += 1.5
    kw = fxlib._kws(beat["text"])
    ck = fxlib._kws(" ".join([card.get("title", ""), card.get("intent", ""),
                              card.get("desc", ""), " ".join(card.get("tags") or [])]))
    sc += 2.0 * min(1.0, len(kw & ck) / 6.0)
    if energy and card.get("energy") == energy:
        sc += 0.6
    if card.get("priority") in ("P0", "P1"):
        sc += 0.4
    sc -= 1.6 * used.get(card["id"], 0)       # 全片尽量不重复用同一个效果
    return sc


def _candidates(args):
    idx = runtime.load_index()
    out = []
    for c in idx["items"]:
        if c.get("status") != "ready" or c.get("kind") == "transition" or not c.get("entry"):
            continue
        req = c.get("requires") or []
        if req and not all(getattr(args, r, None) for r in req):
            continue        # frame_zoom 这类必须有截图，没给就别选
        out.append(c)
    return out


def _pool_for(beat: dict):
    names = []
    for b in (beat.get("beats") or [beat["beat"]]):
        names.extend(BEAT_POOL.get(b, []))
    return set(names) or None


STRUCT_FX = {"bar_grow", "compare_bars", "stacked_bar", "percent_donut",
             "rank_shift", "line_chart", "metric_cards"}


def _eligible(card: dict, sent: str) -> bool:
    """数据类只在句子真的有数/量词时才允许上，否则就是硬套卡。

    结构性图表（柱/环/折线/堆叠）要求至少两个数据点或明确的构成描述；
    一个「上千字」只配得上数字滚动，不该配一张堆叠条。
    """
    fid = card["id"]
    if fid not in DATA_FX:
        return True
    nums = re.findall(r"\d+(?:\.\d+)?", sent)
    quant = any(k in sent for k in ("%", "百分之", "倍", "千", "万", "亿", "字", "轮", "次",
                                    "占比", "比例", "排名", "增长", "下降", "数据", "成"))
    if not (nums or quant):
        return False
    if fid in STRUCT_FX:
        return (len(nums) >= 2 or sent.count("、") >= 2
                or any(k in sent for k in ("分别", "分成", "占比", "构成", "包括", "顺序")))
    return True


def cmd_plan(a) -> int:
    text = Path(a.script).read_text(encoding="utf-8")
    beats = fxlib._split_beats(text)
    cands = _candidates(a)
    by_id = {c["id"]: c for c in cands}
    used, rows, cursor = {}, [], 0.0
    for i, b in enumerate(beats):
        pool = _pool_for(b)
        ok = [c for c in cands if _eligible(c, b["text"])]
        pooled = [c for c in ok if pool is None or c["id"] in pool] or ok
        ranked = sorted(pooled, key=lambda c: -_score(c, b, used, a.energy))
        top = ranked[0]
        s = _score(top, b, used, a.energy)
        if s < a.threshold:
            fb = next((x for x in FALLBACK if x in by_id and x not in used), None)
            if fb is None:               # 全用过就挑用得最少的，别硬重复
                fb = min((x for x in FALLBACK if x in by_id), key=lambda x: used.get(x, 0))
            card = by_id.get(fb, top)
            shot = {"i": i + 1, "kind": "shot", "beat": b["beat"], "text": b["text"],
                    "fx": card["id"], "params": _fill(card.get("auto"), b["text"], a),
                    "why": f"低置信({s:.1f}) → 基础文字动效兜底，不硬套数据卡"}
        else:
            shot = {"i": i + 1, "kind": "shot", "beat": b["beat"], "text": b["text"],
                    "fx": top["id"], "params": _fill(top.get("auto"), b["text"], a),
                    "why": f"{top['title']}（匹配分 {s:.1f}）"}
        used[shot["fx"]] = used.get(shot["fx"], 0) + 1
        shot["dur"] = round(max(a.min_dur, min(a.max_dur, len(b["text"]) * 0.18 + 0.7)), 2)
        shot["at"] = round(cursor, 2)
        cursor += shot["dur"]
        rows.append(shot)
        if a.with_transitions and i < len(beats) - 1 and (i + 1) % a.trans_every == 0:
            fx = TRANS_CYCLE[i % len(TRANS_CYCLE)]
            tp = {"dur": a.trans_dur}
            if a.a:
                tp["a"] = a.a
            if a.b:
                tp["b"] = a.b
            rows.append({"i": f"t{i + 1}", "kind": "transition", "fx": fx,
                         "params": tp, "dur": a.trans_dur,
                         "at": round(cursor, 2), "why": "段间转场"})
            cursor += a.trans_dur
    plan = {
        "version": 1,
        "source": str(Path(a.script).resolve()),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fps": a.fps,
        "energy": a.energy,
        "effects_root": str(runtime.root()),
        "candidates": len(cands),
        "total": round(cursor, 2),
        "shots": rows,
    }
    Path(a.out).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"[{r['i']:>3}] {r['fx'] or '(无)':20s} {r['dur']:.2f}s  {r['why'][:48]}")
    print(f"\n已写 {a.out} · {len(rows)} 条 · 总时长 {cursor:.2f}s · 候选效果 {len(cands)} 个")
    return 0


# ------------------------------------------------------------------ 渲染
def cmd_render(a) -> int:
    plan = json.loads(Path(a.shots).read_text(encoding="utf-8"))
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = int(a.fps or plan.get("fps", 30))
    todo = [s for s in plan["shots"] if s.get("fx")]
    if a.limit:
        todo = todo[: a.limit]
    manifest = []
    for n, s in enumerate(todo, 1):
        p = dict(s.get("params") or {})
        dur = float(s["dur"])
        if s["kind"] == "transition":
            p.setdefault("dur", min(dur, 0.8))
        out = out_dir / f"{n:02d}_{s['fx']}.mp4"
        print(f"渲染 {n}/{len(todo)}  {s['fx']}  {dur:.2f}s -> {out.name}", flush=True)
        try:
            runtime.render_clip(s["fx"], dur, out, p, fps=fps, force=a.force)
            manifest.append({"file": out.name, "fx": s["fx"], "dur": dur,
                             "at": s.get("at"), "kind": s["kind"]})
        except Exception as e:
            print(f"  失败：{type(e).__name__}: {e}", file=sys.stderr)
            manifest.append({"file": None, "fx": s["fx"], "dur": dur, "error": str(e)})
    mf = out_dir / "manifest.json"
    mf.write_text(json.dumps({"fps": fps, "clips": manifest,
                              "ok": sum(1 for x in manifest if x["file"])},
                             ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成 {sum(1 for x in manifest if x['file'])}/{len(todo)} · 清单 {mf}")
    return 0 if all(x["file"] for x in manifest) else 1


def cmd_emit(a) -> int:
    plan = json.loads(Path(a.shots).read_text(encoding="utf-8"))
    lines = ["shots = ["]
    for s in plan["shots"]:
        if not s.get("fx"):
            continue
        cfg = {"fx": s["fx"], "params": s.get("params") or {}}
        lines.append(f"    (\"fx\", {json.dumps(cfg, ensure_ascii=False)}, None, None, None, "
                     f"{s['dur']:.2f}),  # {s['text'][:24] if s.get('text') else s['kind']}")
    lines.append("]")
    print("\n".join(lines))
    return 0


def cmd_preview(a) -> int:
    p = json.loads(a.params) if a.params else {}
    img = runtime.render_frame(a.fx, a.at, a.total, p)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0


def cmd_check(_a) -> int:
    r = runtime.self_check()
    bad = {k: v for k, v in r.items() if v != "OK"}
    for k, v in bad.items():
        print(f"异常 {k}: {v}")
    print(f"自检 {len(r)} 个可运行效果 · 异常 {len(bad)} 个 · 库 {runtime.root()}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ReelForge 稿子 → 镜头表 → 片段")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check").set_defaults(fn=cmd_check)

    p = sub.add_parser("plan")
    p.add_argument("--script", required=True)
    p.add_argument("--out", default="shots.json")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--energy", default="")
    p.add_argument("--threshold", type=float, default=2.6)
    p.add_argument("--min-dur", type=float, default=2.0)
    p.add_argument("--max-dur", type=float, default=4.2)
    p.add_argument("--trans-every", type=int, default=3, help="每几拍插一个转场")
    p.add_argument("--image", default="", help="有截图时允许选 frame_zoom 这类效果")
    p.add_argument("--target", default="", help="标注区域 json，如 [820,470,280,120]")
    p.add_argument("--focus", default="")
    p.add_argument("--with-transitions", action="store_true")
    p.add_argument("--trans-dur", type=float, default=0.55)
    p.add_argument("--a", default="", help="转场前帧：图片或视频路径")
    p.add_argument("--b", default="", help="转场后帧：图片或视频路径")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("render")
    p.add_argument("--shots", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--fps", type=int, default=0)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("emit")
    p.add_argument("--shots", required=True)
    p.set_defaults(fn=cmd_emit)

    p = sub.add_parser("preview")
    p.add_argument("--fx", required=True)
    p.add_argument("--at", type=float, default=1.2)
    p.add_argument("--total", type=float, default=3.0)
    p.add_argument("--params", default="{}")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_preview)

    a = ap.parse_args()
    if getattr(a, "target", ""):
        a.target = json.loads(a.target)
    if getattr(a, "focus", ""):
        a.focus = json.loads(a.focus)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
