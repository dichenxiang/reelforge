"""双人模式的总控助手：把「人当总控」这件事脚本化。

    python duo.py start  --work work/x --title "片名"
    python duo.py handoff --work work/x --persona ace --budget 40
    python duo.py intake --work work/x
    python duo.py gate   --work work/x --name script_gate --ask "这段口播可以吗？"
    python duo.py approve --work work/x --gate script_gate --note "过"
    python duo.py status --work work/x

所有重活（状态机、参考度审计、任务包、wvp 输入）都转交给 reelforge 的脚本，
这里只做双人模式特有的那几件事：生成交接稿、收稿校验、给人生成确认卡。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def reelforge_home() -> Path:
    """找总控 skill（duo 依赖它的 state/similarity/pack_task 脚本）。

    按 agent 的 skill 目录依次找，谁装了就算谁的。
    """
    env = os.environ.get("REELFORGE_HOME")
    if env:
        p = Path(env).expanduser()
        if (p / "scripts" / "state.py").exists():
            return p
    home = Path.home()
    cands = [
        home / ".workbuddy" / "skills" / "reelforge",
        home / ".dsh" / "skills" / "reelforge",
        home / ".codex" / "skills" / "reelforge",
        home / ".claude" / "skills" / "reelforge",
        home / ".gemini" / "antigravity" / "skills" / "reelforge",
    ]
    for c in cands:
        if (c / "scripts" / "state.py").exists():
            return c
    raise SystemExit(
        "[duo] 找不到总控 skill（reelforge）。装一份：bash install.sh --dsh\n"
        "        或设环境变量 REELFORGE_HOME 指向它。"
    )


def rf_scripts() -> Path:
    return reelforge_home() / "scripts"


def run_rf(script: str, *args: str) -> tuple[int, str]:
    exe = sys.executable
    proc = subprocess.run(
        [exe, str(rf_scripts() / script), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- commands

def cmd_start(a) -> int:
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    rc, out = run_rf("state.py", "init", "--work", str(work), "--title", a.title or work.name)
    if rc != 0 and "已存在" not in out:
        print(out)
        return rc
    print(json.dumps({"ok": True, "work": str(work.resolve()),
                      "next": "python duo.py handoff --work " + str(work)}, ensure_ascii=False))
    return 0


def cmd_handoff(a) -> int:
    work = Path(a.work)
    src = work / "tasks" / "writer.md"
    if a.fresh or not src.exists():
        rc, out = run_rf("pack_task.py", "writer", "--work", str(work),
                         "--persona", a.persona, "--budget", str(a.budget))
        if rc != 0:
            print(out)
            return rc
    if not src.exists():
        print("[duo] 没生成 tasks/writer.md")
        return 2
    header = f"""<!-- reelforge-duo · 交给写稿 agent 的交接稿 -->
<!-- 片名：{a.title or work.name} ｜ 生成时间：{now()} -->
<!-- 用法：把本文件整段粘给写稿 agent（Antigravity 等）。
     写完让它把 source_digest.md / script.md / outline.md / script.json / writer-notes.md 五个文件交回你，
     放到 {work.resolve()}/ 下，然后执行：python duo.py intake --work {work} -->

"""
    body = src.read_text(encoding="utf-8")
    extra = []
    if a.topic:
        extra.append(f"## 本次要回答的问题\n\n{a.topic}\n")
    # 执行侧补充的要求与已核实事实
    req = work / "requirements.md"
    if req.exists():
        extra.append("## 本片必须覆盖的段落与写作口径（执行侧补充）\n\n"
                     + req.read_text(encoding="utf-8").strip() + "\n")
    facts = work / "facts.md"
    if facts.exists():
        extra.append("## 工程侧已核实的事实（可直接引用，别在口播里念价格）\n\n"
                     + facts.read_text(encoding="utf-8").strip() + "\n")
    if a.reference:
        extra.append(
            "## 参考稿（学写法，不抄句子）\n\n"
            "以下是我们自己号的真实口播转写，Antigravity 可直接读这些文件：\n\n"
            + "\n".join(f"- `{r}`" for r in a.reference)
            + "\n\n怎么用：\n"
            "- **学**：骨架顺序、句长与节奏、数字密度、每节信息量、称呼与口语连接词、收尾方式\n"
            "- **不学**：原句、同义替换句、具体案例与数字（这些只是结构参照）\n"
            "- 你稿子里的内容只能来自本次检索结果（`source_digest.md`）\n"
            "- 参考度默认 40、硬上限 60，`similarity.py` 会算，超了必须换结构\n"
        )
    if a.link:
        extra.append("## 本次要检索的链接（先检索取证，写进 source_digest.md）\n\n"
                     + "\n".join(f"- {u}" for u in a.link) + "\n")
    if extra:
        anchor = "## 约束" if "## 约束" in body else "## 硬约束"
        body = body.replace(anchor, "\n".join(extra) + "\n" + anchor, 1)
    dst = work / "handoff.writer.md"
    dst.write_text(header + body, encoding="utf-8")
    (work / "links.json").write_text(json.dumps({
        "topic": a.topic or "", "links": a.link or [],
        "persona": a.persona, "budget": a.budget, "created_at": now(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "handoff": str(dst),
        "paste_to": "写稿 agent（Antigravity）",
        "expect_back": ["source_digest.md", "script.md", "outline.md", "script.json", "writer-notes.md"],
        "then": f"python duo.py intake --work {work}",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_intake(a) -> int:
    work = Path(a.work)
    missing = [f for f in ("script.md", "script.json", "writer-notes.md", "outline.md")
               if not (work / f).exists()]
    # 校验稿子确实出自写稿 agent
    notes = work / "writer-notes.md"
    if notes.exists():
        txt = notes.read_text(encoding="utf-8", errors="replace")
        if "writer-agent:" not in txt:
            missing.append("writer-notes.md 里缺少 `writer-agent:` 标记（稿子可能不是写稿 agent 写的）")
    links_file = work / "links.json"
    if links_file.exists():
        try:
            links = json.loads(links_file.read_text(encoding="utf-8")).get("links") or []
        except Exception:
            links = []
        if links and not (work / "source_digest.md").exists():
            missing.append("source_digest.md（给了检索链接，写稿 agent 必须交检索结果）")
    if missing:
        print(json.dumps({
            "ok": False,
            "missing": missing,
            "hint": "把写稿 agent 的产出放回工作目录后再跑 intake",
            "work": str(work.resolve()),
        }, ensure_ascii=False, indent=2))
        return 2
    rc, out = run_rf("similarity.py", "--work", str(work),
                     "--target", str(a.target), "--max", str(a.max))
    try:
        audit = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except Exception:
        audit = {"raw": out}
    run_rf("state.py", "set", "--work", str(work), "--stage", "script",
           "--status", "awaiting_user", "--owner", "duo",
           "--artifacts", str(work / "script.md"))
    verdict = audit.get("verdict")
    if verdict == "fail":
        print(json.dumps({
            "ok": False, "audit": audit,
            "action": "超参考度上限：把 handoff.writer.md 重新发给写稿 agent，要求换结构（不是换词）",
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({
        "ok": True, "audit": audit,
        "gate": "script_gate",
        "ask": f"请看 {work / 'script.md'}，确认后执行：python duo.py approve --work {work} --gate script_gate",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_gate(a) -> int:
    work = Path(a.work)
    rc, out = run_rf("state.py", "gate", "--work", str(work), "--name", a.name)
    card = f"""
──────────── 验收卡 ────────────
门：{a.name}
工作目录：{work.resolve()}
问题：{a.ask}
产物：{', '.join(str(p) for p in a.artifact or []) or '（见工作目录）'}
通过就回我「过」，我会执行：
  python duo.py approve --work {work} --gate {a.name} --note "你的原话"
──────────────────────────────
"""
    print(card)
    return 0


def cmd_approve(a) -> int:
    work = Path(a.work)
    rc, out = run_rf("state.py", "approve", "--work", str(work), "--gate", a.gate, "--note", a.note or "")
    print(out)
    return rc


def cmd_status(a) -> int:
    work = Path(a.work)
    rc, out = run_rf("state.py", "show", "--work", str(work))
    print(out)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="reelforge 双人模式助手")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start"); p.add_argument("--work", required=True); p.add_argument("--title", default="")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("handoff")
    p.add_argument("--work", required=True)
    p.add_argument("--persona", default="ace")
    p.add_argument("--budget", type=int, default=40)
    p.add_argument("--title", default="")
    p.add_argument("--topic", default="", help="本次要回答的问题（给写稿 agent）")
    p.add_argument("--link", action="append", default=[], help="要检索的链接，可多次")
    p.add_argument("--fresh", action="store_true", help="重新生成 tasks/writer.md（默认保留执行者改过的版本）")
    p.add_argument("--reference", action="append", default=[], help="参考稿（转写文件）路径，可多次")
    p.set_defaults(fn=cmd_handoff)

    p = sub.add_parser("intake")
    p.add_argument("--work", required=True)
    p.add_argument("--target", type=int, default=40)
    p.add_argument("--max", type=int, default=60)
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("gate")
    p.add_argument("--work", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--ask", default="这一步可以过吗？")
    p.add_argument("--artifact", action="append")
    p.set_defaults(fn=cmd_gate)

    p = sub.add_parser("approve")
    p.add_argument("--work", required=True)
    p.add_argument("--gate", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("status"); p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_status)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
