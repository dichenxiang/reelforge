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
    env = os.environ.get("REELFORGE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".workbuddy" / "skills" / "reelforge"


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
    rc, out = run_rf("pack_task.py", "writer", "--work", str(work),
                     "--persona", a.persona, "--budget", str(a.budget))
    if rc != 0:
        print(out)
        return rc
    src = work / "tasks" / "writer.md"
    if not src.exists():
        print("[duo] 没生成 tasks/writer.md")
        return 2
    header = f"""<!-- reelforge-duo · 交给写稿 agent 的交接稿 -->
<!-- 片名：{a.title or work.name} ｜ 生成时间：{now()} -->
<!-- 用法：把本文件整段粘给写稿 agent（Antigravity 等）。
     写完让它把 script.md / script.json / writer-notes.md 三个文件交回你，
     放到 {work.resolve()}/ 下，然后执行：python duo.py intake --work {work} -->

"""
    dst = work / "handoff.writer.md"
    dst.write_text(header + src.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "handoff": str(dst),
        "paste_to": "写稿 agent（Antigravity）",
        "expect_back": ["script.md", "script.json", "writer-notes.md"],
        "then": f"python duo.py intake --work {work}",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_intake(a) -> int:
    work = Path(a.work)
    missing = [f for f in ("script.md", "script.json") if not (work / f).exists()]
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
