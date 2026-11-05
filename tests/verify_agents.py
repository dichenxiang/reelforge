#!/usr/bin/env python3
"""跨 agent 同步校验：确认每个 agent 的技能目录都是最新版、效果库可被独立调用。

用法：
    python tests/verify_agents.py            # 只查文件一致性（快）
    python tests/verify_agents.py --smoke    # 额外让每个目录独立渲一个片段（需 ffmpeg）

任一目录不一致 / 冒烟失败，退出码非 0。同步用 `bash install.sh --all`（先备份再覆盖式更新，不删目录）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path.home()
SRC = REPO / "skills" / "reelforge"

TARGETS = {
    "workbuddy": HOME / ".workbuddy" / "skills",
    "codex": HOME / ".codex" / "skills",
    "claude": HOME / ".claude" / "skills",
    "gemini_cli": HOME / ".gemini" / "skills",
    "antigravity": HOME / ".gemini" / "antigravity" / "skills",
    "deepseek_harness": HOME / ".dsh" / "skills",
}

# 少一个就说明这个 agent 拿到的是旧版，出片会缺动效
KEY = [
    "SKILL.md", "AGENT_ROUTING.md",
    "scripts/fx_pipeline.py", "scripts/effects.py",
    "effects/runtime.py", "effects/index.json",
    "effects/fx/data_pack.py", "effects/fx/trans_pack.py",
    "effects/fx/text_pack.py", "effects/fx/annot_pack.py",
    "references/effects-library.md", "references/pitfalls.md",
]
SUB_SKILLS = ["reelforge-writer", "reelforge-runner", "reelforge-duo", "reelforge-router"]


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def src_of(rel: str) -> pathlib.Path:
    # 全部以 skills/reelforge/ 为准：install.sh 分发的就是这个目录
    return SRC / rel


def check_files() -> dict:
    out = {}
    for name, root in TARGETS.items():
        rf = root / "reelforge"
        if not rf.exists():
            out[name] = {"ok": False, "missing": ["<整个 reelforge 目录>"]}
            continue
        missing, diff = [], []
        for rel in KEY:
            s, d = src_of(rel), rf / rel
            if not d.exists():
                missing.append(rel)
            elif md5(s) != md5(d):
                diff.append(rel)
        for k in SUB_SKILLS:
            s, d = REPO / "skills" / k / "SKILL.md", root / k / "SKILL.md"
            if not d.exists():
                missing.append(f"{k}/SKILL.md")
            elif md5(s) != md5(d):
                diff.append(f"{k}/SKILL.md")
        out[name] = {"ok": not missing and not diff, "missing": missing, "diff": diff}
    return out


def smoke(name: str, root: pathlib.Path) -> tuple[bool, str]:
    """空本地库 + 独立 cwd：证明这个目录不依赖别的 agent、不依赖 ~/.reelforge。"""
    fx = root / "reelforge" / "scripts" / "fx_pipeline.py"
    with tempfile.TemporaryDirectory(prefix="rf_verify_") as td:
        wd = pathlib.Path(td)
        (wd / "script.txt").write_text("这些视频的提示词，到底长什么样？\n", encoding="utf-8")
        (wd / "empty").mkdir()
        env = dict(os.environ)
        env["REELFORGE_EFFECTS"] = str(wd / "empty")
        for args in (["check"],
                     ["plan", "--script", str(wd / "script.txt"),
                      "--out", str(wd / "shots.json")],
                     ["render", "--shots", str(wd / "shots.json"),
                      "--out-dir", str(wd / "clips"), "--limit", "1", "--fps", "10"]):
            p = subprocess.run([sys.executable, str(fx)] + args, cwd=wd, env=env,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if p.returncode:
                return False, f"{' '.join(args[:1])} 失败: {(p.stderr or p.stdout).strip()[-200:]}"
        clips = list((wd / "clips").glob("*.mp4"))
        return bool(clips), "产出 mp4" if clips else "没产出 mp4"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="额外逐目录渲一个片段")
    a = ap.parse_args()
    res = check_files()
    ok = True
    print("ReelForge 跨 agent 校验  仓库:", REPO)
    for name, root in TARGETS.items():
        r = res[name]
        line = f"  {name:18s} {'OK' if r['ok'] else '不一致'}"
        if not r["ok"]:
            line += f"  缺={r['missing']}  异={r['diff']}"
            ok = False
        if a.smoke and r["ok"]:
            good, msg = smoke(name, root)
            line += f"  冒烟={'OK' if good else 'FAIL'} {msg}"
            ok &= good
        print(line)
    if not (HOME / ".reelforge" / "AGENT_ROUTING.md").exists():
        print("  ⚠ 统一路由未写入 ~/.reelforge/AGENT_ROUTING.md")
        ok = False
    print("结论:", "六个目标全部可用" if ok else "有目录需要重新同步（bash install.sh --all）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
