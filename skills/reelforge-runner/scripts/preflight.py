"""preflight.py —— 开工前体检：把“第 4 步才炸”的缺依赖提前到第 0 步。

    python scripts/preflight.py
    python scripts/preflight.py --json
    python scripts/preflight.py --work work/demo      # 结果写进 work/demo/preflight.json

退出码：0 = 硬性依赖齐全；1 = 缺硬性依赖（python/ffmpeg/wvp）；软缺失只提示。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HARD = {"python", "ffmpeg", "ffprobe"}


def which(name: str) -> str | None:
    p = shutil.which(name)
    if p:
        return p
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return shutil.which(name + ".exe")
    return None


def check_python() -> dict:
    ok = sys.version_info >= (3, 10)
    return {"name": "python", "ok": ok, "detail": platform.python_version(),
            "hint": "" if ok else "需要 Python 3.10+"}


def check_node() -> dict:
    exe = which("node")
    if not exe:
        return {"name": "node", "ok": False, "detail": "未找到", "hint": "装 Node 18+：https://nodejs.org"}
    try:
        v = subprocess.run([exe, "-v"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10).stdout.strip()
        major = int(v.lstrip("v").split(".")[0])
        return {"name": "node", "ok": major >= 18, "detail": v, "hint": "" if major >= 18 else "需要 Node 18+"}
    except Exception as e:
        return {"name": "node", "ok": False, "detail": str(e), "hint": "重装 Node"}


def check_bin(name: str) -> dict:
    p = which(name)
    return {"name": name, "ok": bool(p), "detail": p or "未找到",
            "hint": "" if p else f"装 {name}（Windows: winget install Gyan.FFmpeg / choco install ffmpeg）"}


def check_jq() -> dict:
    p = which("jq")
    return {"name": "jq", "ok": bool(p), "detail": p or "未找到",
            "hint": "" if p else "synthesize-audio 需要 jq；Windows: winget install jqlang.jq"}


def check_wvp(skill_root: Path) -> dict:
    p = skill_root / "vendor" / "web-video-presentation" / "scripts" / "scaffold.sh"
    return {"name": "wvp", "ok": p.exists(), "detail": str(p) if p.exists() else "vendor 缺失",
            "hint": "" if p.exists() else "bash install.sh --with-wvp 拉取 web-video-presentation"}


def check_index_tts() -> dict:
    for url in ("http://127.0.0.1:7860/",):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return {"name": "IndexTTS", "ok": True, "detail": f"{url} 可达", "hint": ""}
        except Exception:
            pass
    return {"name": "IndexTTS", "ok": False, "detail": "127.0.0.1:7860 不可达（会按 tts.yaml 自动拉起）",
            "hint": "无 GPU 可改用 edge-tts：pip install edge-tts"}


def check_edge_tts() -> dict:
    ok = importlib.util.find_spec("edge_tts") is not None
    return {"name": "edge-tts", "ok": ok, "detail": "已装" if ok else "未装",
            "hint": "" if ok else "pip install edge-tts（无 GPU 的兜底音色）"}


def check_browser() -> dict:
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/microsoft-edge",
        "/usr/bin/google-chrome",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    for c in cands:
        if Path(c).exists():
            return {"name": "browser", "ok": True, "detail": c, "hint": ""}
    return {"name": "browser", "ok": False, "detail": "未找到 Edge/Chrome",
            "hint": "装 Edge，或用 playwright 自带 chromium（npx playwright install chromium）"}


def check_playwright() -> dict:
    for pkg in ("playwright-core", "playwright"):
        try:
            out = subprocess.run(["node", "-e", f"require.resolve('{pkg}')"],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, cwd=os.getcwd())
            if out.returncode == 0:
                return {"name": "playwright", "ok": True, "detail": pkg, "hint": ""}
        except Exception:
            pass
    return {"name": "playwright", "ok": False, "detail": "工程里未安装 playwright-core/playwright",
            "hint": "cd presentation && npm i -D playwright-core（复用本机 Edge 即可）"}


def check_personas(skill_root: Path) -> dict:
    cfg = skill_root / "config"
    local = cfg / "personas.local.yaml"
    example = cfg / "personas.example.yaml"
    if local.exists():
        return {"name": "personas", "ok": True, "detail": str(local), "hint": ""}
    return {"name": "personas", "ok": False, "detail": "还没生成本地人设",
            "hint": f"python {skill_root}/scripts/personas_init.py（或 cp {example} → personas.local.yaml）"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--work", default="")
    a = ap.parse_args()

    skills_dir = Path(__file__).resolve().parents[2]
    skill_root = skills_dir / "reelforge"
    if not (skill_root / "scripts").exists():
        skill_root = Path(__file__).resolve().parent.parent
    checks = [check_python(), check_node(), check_bin("ffmpeg"), check_bin("ffprobe"),
              check_jq(), check_wvp(skill_root), check_browser(), check_playwright(),
              check_index_tts(), check_edge_tts(), check_personas(skill_root)]

    hard_ok = all(c["ok"] for c in checks if c["name"] in HARD)
    payload = {"ok": hard_ok, "platform": platform.platform(), "checks": checks}

    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ReelForge preflight · {platform.platform()}\n")
        for c in checks:
            mark = "[OK]" if c["ok"] else "[!!]"
            print(f"  {mark} {c['name']:<12} {c['detail']}")
            if not c["ok"] and c["hint"]:
                print(f"      → {c['hint']}")
        print()
        hard_missing = [c["name"] for c in checks if c["name"] in HARD and not c["ok"]]
        if hard_missing:
            print(f"结论：缺硬性依赖 {hard_missing}，先补齐再开工")
        else:
            print("结论：硬性依赖齐全，可以开工")
            if not any(c["name"] == "IndexTTS" and c["ok"] for c in checks) and \
               not any(c["name"] == "edge-tts" and c["ok"] for c in checks):
                print("      旁白：两条路都不可用，先装 IndexTTS 或 edge-tts")

    if a.work:
        w = Path(a.work)
        w.mkdir(parents=True, exist_ok=True)
        (w / "preflight.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if hard_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
