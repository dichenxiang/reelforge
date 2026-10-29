"""一次性环境自检。第一次用这个 skill 时跑它。

    python probe.py

只读，不改任何东西。缺什么会给出确切安装命令。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, VENDOR, find_bin  # noqa: E402


def has_mod(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check(label: str, ok: bool, detail: str = "", fix: str = "") -> dict:
    icon = "ok " if ok else "!! "
    print(f"[{icon}] {label}{('  ' + detail) if detail else ''}")
    if not ok and fix:
        print(f"       → {fix}")
    return {"label": label, "ok": ok, "detail": detail, "fix": fix}


def main() -> int:
    print(f"video-factory @ {SKILL_DIR}\n")
    r = []

    py_ok = sys.version_info >= (3, 10)
    r.append(check("python 3.10+", py_ok, sys.version.split()[0], "装 Python 3.11+"))

    for mod, fix in [
        ("faster_whisper", "python -m pip install faster-whisper"),
        ("ctranslate2", "python -m pip install ctranslate2"),
        ("yt_dlp", "python -m pip install -U yt-dlp"),
        ("PIL", "python -m pip install pillow"),
        ("edge_tts", "python -m pip install edge-tts"),
        ("yaml", "python -m pip install pyyaml"),
    ]:
        r.append(check(mod, has_mod(mod), "", fix))

    for name in ("ffmpeg", "ffprobe"):
        try:
            p = find_bin(name)
            r.append(check(name, True, str(p)))
        except SystemExit as e:
            r.append(check(name, False, "", str(e)))

    node = shutil.which("node")
    node_ver = ""
    if node:
        try:
            node_ver = subprocess.run([node, "-v"], capture_output=True, text=True, timeout=20).stdout.strip()
        except subprocess.SubprocessError:
            pass
    node_ok = bool(node) and int((node_ver or "v0").lstrip("v").split(".")[0] or 0) >= 18
    r.append(check("node 18+", node_ok, node_ver, "winget install OpenJS.NodeJS.LTS"))

    jq = shutil.which("jq")
    r.append(check("jq", bool(jq), jq or "", "winget install jqlang.jq，或把 jq.exe 放进 PATH"))

    wvp = VENDOR / "web-video-presentation"
    r.append(check("web-video-presentation vendor", (wvp / "SKILL.md").exists(),
                   str(wvp), "skill 安装不完整，重新拷贝 vendor/web-video-presentation"))

    npm = shutil.which("npm")
    r.append(check("npm", bool(npm), npm or "", "随 Node.js 一起安装"))

    if node_ok:
        chrome = [
            os.environ.get("CHROME_PATH"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        sys_browser = next((p for p in chrome if p and Path(p).exists()), None)
        r.append(check("browser", bool(sys_browser), sys_browser or "",
                       "装 Chrome 或 Edge，用于预览与录屏"))

    # 转写能真跑（加载一次模型，3 秒内返回即可）
    if has_mod("faster_whisper"):
        try:
            from _common import setup_cuda_dlls
            setup_cuda_dlls()
            from faster_whisper import WhisperModel
            WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")
            r.append(check("faster-whisper CUDA", True, "large-v3-turbo / int8_float16"))
        except Exception as e:  # noqa: BLE001
            r.append(check("faster-whisper CUDA", False, type(e).__name__,
                           "装 nvidia-cublas-cu12 + nvidia-cudnn-cu12；或改 --device cpu --compute int8"))

    print("\nAntigravity 桥接（MCP）不在本脚本检查范围：用 mcp__antigravity__health 工具确认。")
    bad = [x for x in r if not x["ok"]]
    print(json.dumps({"ok": not bad, "missing": [x["label"] for x in bad]}, ensure_ascii=False))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
