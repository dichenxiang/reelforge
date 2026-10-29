#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Antigravity Bridge — 用 Antigravity 内置模型（Google 订阅额度，无需 API Key）
以非交互方式驱动 agent 会话。

用法:
  python ag_bridge.py models
  python ag_bridge.py run --model flash --title "视频分析" --timeout 600 "你的 prompt"
  python ag_bridge.py run --model flash --prompt-file prompt.txt
  python ag_bridge.py wait <conversation_id>

机制:
  1. 从运行中的 language_server.exe 进程命令行取 --csrf_token
  2. 从 %APPDATA%/Antigravity/logs/language_server.log 取最新 HTTP 端口
  3. 调用 `language_server.exe agentapi new-conversation`
  4. 轮询 brain/<id>/.system_generated/logs/transcript.jsonl 直到本轮结束
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
AG_DIR = HOME / ".gemini" / "antigravity"
LOG_FILE = Path(os.environ.get("APPDATA", "")) / "Antigravity" / "logs" / "language_server.log"
_local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
LS_EXE = Path(os.environ.get(
    "ANTIGRAVITY_LS_EXE",
    str(_local / "Programs" / "antigravity" / "resources" / "bin" / "language_server.exe"),
))


def _log(msg: str) -> None:
    print(f"[ag_bridge] {msg}", file=sys.stderr, flush=True)


def discover(timeout_check: float = 3.0) -> tuple[str, str]:
    """返回 (port, csrf_token)。优先进程命令行 + 日志，失败则扫端口。"""
    csrf = None
    port = None

    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='language_server.exe'\" "
                "| Select-Object -ExpandProperty CommandLine",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        for line in out.splitlines():
            m = re.search(r"--csrf_token[= ]([0-9a-fA-F\-]{8,})", line)
            if m:
                csrf = m.group(1)
    except Exception as e:  # pragma: no cover
        _log(f"读取进程命令行失败: {e}")

    if LOG_FILE.exists():
        try:
            txt = LOG_FILE.read_text(encoding="utf-8", errors="replace")
            ports = re.findall(r"listening on random port at (\d+) for HTTP", txt)
            if ports:
                port = ports[-1]
        except Exception as e:  # pragma: no cover
            _log(f"读取日志失败: {e}")

    if not port or not csrf:
        # 兜底：扫描常见端口段，找 /healthz 可用且页面带 csrfToken 的实例
        for p in list(range(8890, 8911)) + list(range(5000, 5010)) + [8894, 8895]:
            try:
                r = subprocess.run(
                    ["curl", "-s", "-m", "1", "--noproxy", "*", f"http://127.0.0.1:{p}/healthz"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if '"status":"ok"' not in (r.stdout or ""):
                    continue
                page = subprocess.run(
                    ["curl", "-s", "-m", "1", "--noproxy", "*", f"http://127.0.0.1:{p}/"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout
                m = re.search(r'"csrfToken":"([^"]+)"', page or "")
                if m:
                    port, csrf = str(p), m.group(1)
                    break
            except Exception:
                continue

    if not port or not csrf:
        raise RuntimeError(
            "找不到运行中的 Antigravity 实例。请先打开 Antigravity 桌面端，确认它没有退出。"
        )
    return port, csrf


def _env(port: str, csrf: str) -> dict:
    env = os.environ.copy()
    env["ANTIGRAVITY_LS_ADDRESS"] = f"localhost:{port}"
    env["ANTIGRAVITY_CSRF_TOKEN"] = csrf
    env.setdefault("ANTIGRAVITY_LS_VERSION", "2.26.0")
    return env


def _run_agentapi(args: list[str], port: str, csrf: str) -> dict:
    cmd = [str(LS_EXE), "agentapi", *args]
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=_env(port, csrf)
    )
    raw = (r.stdout or "").strip() or (r.stderr or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw, "_rc": r.returncode}


def create_conversation(prompt: str, model: str = "flash", title: str | None = None) -> str:
    port, csrf = discover()
    args = ["new-conversation", f"--model={model}"]
    if title:
        args.append(f"--title={title}")
    args.append(prompt)
    res = _run_agentapi(args, port, csrf)
    if "error" in res and res["error"]:
        raise RuntimeError(f"创建会话失败: {res['error']}")
    cid = res.get("response", {}).get("newConversation", {}).get("conversationId")
    if not cid:
        raise RuntimeError(f"未拿到 conversationId: {res}")
    return cid


def _transcript_path(cid: str) -> Path:
    return AG_DIR / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl"


def read_steps(cid: str) -> list[dict]:
    p = _transcript_path(cid)
    if not p.exists():
        return []
    steps = []
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                steps.append(json.loads(line))
            except Exception:
                continue
    return steps


def wait_done(cid: str, timeout: float = 600.0, quiet: float = 5.0) -> list[dict]:
    """轮询到本轮结束：最后一步是 PLANNER_RESPONSE/DONE 且文件静默 quiet 秒。"""
    t0 = time.time()
    p = _transcript_path(cid)
    last_sig = None
    last_change = time.time()
    last_key = (0, 0)
    while time.time() - t0 < timeout:
        steps = read_steps(cid)
        sig = (p.stat().st_mtime if p.exists() else 0, len(steps))
        if sig != last_sig:
            last_sig = sig
            last_change = time.time()
        if steps:
            last = steps[-1]
            done = last.get("status") == "DONE" and last.get("type") in (
                "PLANNER_RESPONSE",
                "ERROR",
            )
            idle = time.time() - last_change
            if done and idle >= quiet:
                return steps
            if last.get("type") == "ERROR" and idle >= 1.0:
                return steps
        # 进度提示
        key = (len(steps), last_change)
        if key != last_key:
            last_key = key
            _log(f"steps={len(steps)} last={steps[-1].get('type') if steps else '-'} elapsed={int(time.time()-t0)}s")
        time.sleep(1.5)
    raise TimeoutError(f"等待会话 {cid} 超时（{timeout}s）")


def final_answer(steps: list[dict]) -> dict:
    out = {"reply": "", "thinking": "", "steps": len(steps), "tools": [], "error": None}
    for s in steps:
        if s.get("type") == "ERROR":
            out["error"] = s.get("content") or s.get("error") or "unknown error"
        if s.get("type") in ("RUN_COMMAND", "READ_FILE", "CODE_ACTION", "VIEW_FILE", "GREP_SEARCH", "LIST_DIRECTORY"):
            out["tools"].append({"type": s.get("type"), "status": s.get("status")})
    planner = [s for s in steps if s.get("type") == "PLANNER_RESPONSE"]
    if planner:
        last = planner[-1]
        out["reply"] = (last.get("content") or "").strip()
        out["thinking"] = (last.get("thinking") or "").strip()
        # 若最后一条 content 为空，回溯最近的非空 content
        if not out["reply"]:
            for s in reversed(planner):
                if (s.get("content") or "").strip():
                    out["reply"] = s["content"].strip()
                    break
    return out


def cmd_run(a) -> int:
    prompt = a.prompt
    if a.prompt_file:
        prompt = Path(a.prompt_file).read_text(encoding="utf-8")
    if not prompt:
        _log("缺少 prompt")
        return 2
    cid = create_conversation(prompt, a.model, a.title)
    print(json.dumps({"conversation_id": cid, "status": "created"}, ensure_ascii=False), flush=True)
    steps = wait_done(cid, a.timeout)
    ans = final_answer(steps)
    ans["conversation_id"] = cid
    ans["model"] = a.model
    print(json.dumps(ans, ensure_ascii=False, indent=2))
    return 0


def cmd_wait(a) -> int:
    steps = wait_done(a.conversation_id, a.timeout)
    ans = final_answer(steps)
    ans["conversation_id"] = a.conversation_id
    print(json.dumps(ans, ensure_ascii=False, indent=2))
    return 0


def cmd_models(a) -> int:
    port, csrf = discover()
    res = _run_agentapi(["new-conversation", "--help"], port, csrf)
    print(json.dumps({"port": port, "csrf_found": bool(csrf), "help": res.get("_raw", res)[:400]}, ensure_ascii=False, indent=2))
    print("模型档位: flash_lite / flash / pro", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Antigravity 会话桥接（无需 API Key）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="新建会话并等待结果")
    r.add_argument("prompt", nargs="?", default="")
    r.add_argument("--prompt-file")
    r.add_argument("--model", default="flash", choices=["flash_lite", "flash", "pro"])
    r.add_argument("--title", default=None)
    r.add_argument("--timeout", type=float, default=600)
    r.set_defaults(func=cmd_run)

    w = sub.add_parser("wait", help="等待已有会话")
    w.add_argument("conversation_id")
    w.add_argument("--timeout", type=float, default=600)
    w.set_defaults(func=cmd_wait)

    m = sub.add_parser("models", help="检查连接与可用档位")
    m.set_defaults(func=cmd_models)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
