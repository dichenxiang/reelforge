"""把 script.json 转成 wvp 需要的三份输入：script.md / outline.md / article.md。

    python make_wvp_inputs.py --work work/xxx [--force]

映射规则（短视频）：
- 1 个 chapter（slug 或 `main`），N 个 step = script.json 的 N 拍
- script.md 每拍一段，用 --- 分隔（wvp 按节拍切）
- outline.md 每 step 一行，屏幕内容取 beat.visual
- article.md 取 evidence.md（没有就写标题 + 数据来源）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_json, write_json  # noqa: E402


def build_script_md(script: dict, beats: list[dict]) -> str:
    head = [f"# {script.get('title', '未命名')}", ""]
    if script.get("takeaway"):
        head += [f"> 一句话：{script['takeaway']}", ""]
    body = []
    for b in beats:
        body.append((b.get("text") or "").strip())
    return "\n".join(head) + "\n---\n".join(body) + "\n"


def build_outline_md(script: dict, beats: list[dict], chapter_id: str) -> str:
    total = float(script.get("duration_sec") or 0)
    steps = []
    for i, b in enumerate(beats, 1):
        dur = float(b.get("duration_sec") or 0)
        content = (b.get("visual") or "").strip() or (b.get("text") or "").strip()
        steps.append(f"- step {i} (~{dur:.1f}s) — {content}")
    pool = []
    for k in ("takeaway", "hook", "signature"):
        if script.get(k):
            pool.append(f"- 要点：{script[k]}")
    if script.get("source_basis"):
        pool.append(f"- 出处：{script['source_basis']}")
    pool_md = "\n".join(pool) if pool else "- （待补：从 article.md 抽数字 / 对比 / 案例）"
    return f"""# Video Outline

> **主题**：待 Checkpoint Plan 选定
> **总时长**：约 {total:.0f} 秒（口播 ~{sum(len(b.get('text','')) for b in beats)} 字）
> **章节数**：1 章 / {len(beats)} 步

---

## 1. {chapter_id} — {script.get('title', '主章节')}（{len(beats)} steps · ~{total:.0f}s）

**信息池**（chapter agent 按需挂角标 / 副标 / pull-quote）：
{pool_md}

**开发计划**：

{chr(10).join(steps)}

口播节选：
> {(beats[0].get('text') if beats else '')}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    work = Path(a.work)
    script = read_json(work / "script.json")
    beats = [b for b in (script.get("beats") or []) if (b.get("text") or "").strip()]
    if not beats:
        raise SystemExit("[wvp] script.json 没有可用的 beats")

    # writer 若已按 OUTLINE-FORMAT.md 产出 outline.md，就不要用粗版覆盖它
    if (work / "outline.md").exists() and not a.force:
        print("[wvp] outline.md 已存在（写稿 agent 产出），保留；如需覆盖加 --force")
    targets = [work / "script.md", work / "article.md"]
    if not (work / "outline.md").exists():
        targets.append(work / "outline.md")
    if any(t.exists() for t in targets) and not a.force:
        raise SystemExit("[wvp] script.md / outline.md / article.md 已存在，要覆盖加 --force")

    chapter_id = work.name.replace("_", "-")[:24] or "main"
    (work / "script.md").write_text(build_script_md(script, beats), encoding="utf-8")
    if not (work / "outline.md").exists() or a.force:
        (work / "outline.md").write_text(build_outline_md(script, beats, chapter_id), encoding="utf-8")

    ev_md = work / "evidence.md"
    if ev_md.exists():
        article = ev_md.read_text(encoding="utf-8")
    else:
        article = f"# {script.get('title','')}\n\n" + "\n".join(
            f"- {b.get('visual','')}" for b in beats
        ) + "\n"
    (work / "article.md").write_text(article, encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "script": str(work / "script.md"),
        "outline": str(work / "outline.md"),
        "article": str(work / "article.md"),
        "chapter_id": chapter_id,
        "steps": len(beats),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
