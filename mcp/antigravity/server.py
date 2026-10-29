#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP Server: antigravity-bridge
把 Antigravity 桌面端内置的 Gemini 模型（Google 订阅额度，无需 API Key）
暴露为 MCP 工具，供上层 Agent 调用。

协议: MCP over stdio, newline-delimited JSON-RPC 2.0
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

HOME = Path.home()
AG_DIR = HOME / ".gemini" / "antigravity"
LOG_FILE = Path(os.environ.get("APPDATA", "")) / "Antigravity" / "logs" / "language_server.log"
_local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
LS_EXE = Path(os.environ.get(
    "ANTIGRAVITY_LS_EXE",
    str(_local / "Programs" / "antigravity" / "resources" / "bin" / "language_server.exe"),
))
VERSION = "1.0.0"

# ---------------------------------------------------------------- logging
LOG_PATH = Path(os.environ.get("TEMP", tempfile.gettempdir())) / "antigravity_mcp.log"


def log(msg: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------- discovery
_cache: dict = {"ts": 0.0, "port": None, "csrf": None}


def discover(force: bool = False) -> tuple[str, str]:
    now = time.time()
    if not force and _cache["port"] and now - _cache["ts"] < 30:
        return _cache["port"], _cache["csrf"]

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
    except Exception as e:
        log(f"ps fail: {e}")

    if LOG_FILE.exists():
        try:
            txt = LOG_FILE.read_text(encoding="utf-8", errors="replace")
            ports = re.findall(r"listening on random port at (\d+) for HTTP", txt)
            if ports:
                port = ports[-1]
        except Exception as e:
            log(f"log fail: {e}")

    if not port or not csrf:
        for p in [8895, 8894] + list(range(8890, 8910)) + list(range(5000, 5010)):
            try:
                r = subprocess.run(
                    ["curl", "-s", "-m", "1", "--noproxy", "*", f"http://127.0.0.1:{p}/healthz"],
                    capture_output=True, text=True, timeout=3,
                )
                if '"status":"ok"' not in (r.stdout or ""):
                    continue
                page = subprocess.run(
                    ["curl", "-s", "-m", "1", "--noproxy", "*", f"http://127.0.0.1:{p}/"],
                    capture_output=True, text=True, timeout=3,
                ).stdout
                m = re.search(r'"csrfToken":"([^"]+)"', page or "")
                if m:
                    port, csrf = str(p), m.group(1)
                    break
            except Exception:
                continue

    if not port or not csrf:
        raise RuntimeError(
            "找不到运行中的 Antigravity。请先打开 Antigravity 桌面端并保持登录状态。"
        )
    _cache.update({"ts": now, "port": port, "csrf": csrf})
    return port, csrf


def call_agentapi(args: list[str]) -> dict:
    port, csrf = discover()
    env = os.environ.copy()
    env["ANTIGRAVITY_LS_ADDRESS"] = f"localhost:{port}"
    env["ANTIGRAVITY_CSRF_TOKEN"] = csrf
    env.setdefault("ANTIGRAVITY_LS_VERSION", "2.26.0")
    r = subprocess.run(
        [str(LS_EXE), "agentapi", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    raw = (r.stdout or "").strip() or (r.stderr or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        raise RuntimeError(f"agentapi 返回异常: {raw[:500]}")


# ---------------------------------------------------------------- session
def start_session(prompt: str, model: str = "flash", title: str | None = None) -> str:
    args = ["new-conversation", f"--model={model}"]
    if title:
        args.append(f"--title={title[:80]}")
    args.append(prompt)
    res = call_agentapi(args)
    if res.get("error"):
        raise RuntimeError(f"创建会话失败: {res['error']}")
    cid = (res.get("response") or {}).get("newConversation", {}).get("conversationId")
    if not cid:
        raise RuntimeError(f"未拿到 conversationId: {res}")
    return cid


def transcript_path(cid: str) -> Path:
    return AG_DIR / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl"


def read_steps(cid: str) -> list[dict]:
    p = transcript_path(cid)
    if not p.exists():
        return []
    out = []
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def wait_done(cid: str, timeout: float = 900.0, quiet: float = 5.0) -> list[dict]:
    t0 = time.time()
    p = transcript_path(cid)
    last_sig = None
    last_change = time.time()
    while time.time() - t0 < timeout:
        steps = read_steps(cid)
        sig = (p.stat().st_mtime if p.exists() else 0, len(steps))
        if sig != last_sig:
            last_sig = sig
            last_change = time.time()
        if steps:
            last = steps[-1]
            done = last.get("status") == "DONE" and last.get("type") in ("PLANNER_RESPONSE", "ERROR")
            if done and time.time() - last_change >= quiet:
                return steps
            if last.get("type") == "ERROR" and time.time() - last_change >= 1.0:
                return steps
        time.sleep(1.5)
    raise TimeoutError(f"等待会话超时（{timeout}s），会话仍在后台运行: {cid}")


def summarize(cid: str, steps: list[dict]) -> dict:
    planner = [s for s in steps if s.get("type") == "PLANNER_RESPONSE"]
    reply = ""
    for s in reversed(planner):
        if (s.get("content") or "").strip():
            reply = s["content"].strip()
            break
    tools = []
    for s in steps:
        for tc in (s.get("tool_calls") or []):
            if isinstance(tc, dict):
                tools.append(tc.get("name"))
    err = None
    for s in steps:
        if s.get("type") == "ERROR":
            err = s.get("content") or "error"
    return {
        "conversation_id": cid,
        "reply": reply,
        "tool_calls": tools,
        "steps": len(steps),
        "error": err,
    }


# ---------------------------------------------------------------- video utils
def ffmpeg_exe() -> str | None:
    # 优先用完整版 ffmpeg。
    #
    # 原来第一顺位是 imageio_ffmpeg 自带的精简构建，它解不了部分容器/编码
    # （B站、抖音的某些 H.265 与 fragmented mp4），导致 frames>0 抽帧模式
    # 静默失败或卡死。项目里已经有完整版，直接用。
    for p in [
        r"D:\AI-Video-Pipeline\tools\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]:
        if Path(p).exists():
            return p
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    for p in [
        shutil_which("ffmpeg"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]:
        if p and Path(p).exists():
            return p
    return None


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def probe_duration(video: str, ff: str) -> float:
    try:
        r = subprocess.run([ff, "-i", video], capture_output=True, text=True, timeout=60)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", r.stderr or "")
        if m:
            h, mi, se = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(se)
    except Exception:
        pass
    return 0.0


def extract_frames(video: str, n: int) -> tuple[list[Path], float]:
    """按时间点 seek 抽帧。

    原实现用 `-vf fps=R -frames:v N`：fps filter 必须解码到第 N 个输出帧所在的
    时间点才停，也就是说 117 秒视频抽 12 帧要把整片解一遍，实测 600 秒超时。

    改成对每个目标时间点单独 `-ss T -i ... -frames:v 1`：seek 是 O(1) 的，
    单帧解码几十毫秒，整批 1-2 秒完成。均匀取点在段中点，避开首尾的转场黑帧。
    """
    ff = ffmpeg_exe()
    if not ff:
        raise RuntimeError("未找到 ffmpeg，无法抽帧。请安装 imageio-ffmpeg 或系统 ffmpeg。")
    dur = probe_duration(video, ff)
    outdir = Path(tempfile.gettempdir()) / f"ag_frames_{uuid.uuid4().hex[:8]}"
    outdir.mkdir(parents=True, exist_ok=True)

    n = max(int(n), 1)
    if dur > 0:
        # 段中点取点：(i + 0.5) / n 覆盖全片，天然避开首尾
        times = [dur * (i + 0.5) / n for i in range(n)]
    else:
        times = [float(i) for i in range(n)]

    frames: list[Path] = []
    for i, tsec in enumerate(times):
        fp = outdir / f"frame_{i + 1:03d}.jpg"
        cmd = [
            ff, "-y", "-v", "error",
            "-ss", f"{tsec:.3f}", "-i", video,
            "-frames:v", "1", "-q:v", "2", str(fp),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            continue
        if fp.exists() and fp.stat().st_size > 0:
            frames.append(fp)
    return frames, dur


def build_video_prompt(path: str, instruction: str, frames: int) -> str:
    if frames <= 0:
        return (
            "你是视频分析执行器。任务：分析一个本地视频文件。\n\n"
            f"视频路径：{path}\n\n"
            "执行规则：\n"
            "1. 只调用 read_file 读取上面这个文件本身。它是视频，直接按视频理解画面与时间轴。\n"
            "2. 不要运行 ffmpeg / python / 任何命令，不要抽帧，不要读取无关文件。\n"
            "3. 只做只读分析，不要创建或修改任何文件。\n"
            "4. 若确实无法解码画面，明确回答「无法解码」并说明原因。\n\n"
            f"分析要求：\n{instruction}\n\n"
            "输出要求：结构化 Markdown，先给结论，再给证据（时间点 + 画面内容）。不要输出思考过程。"
        )
    fr, dur = extract_frames(path, frames)
    if not fr:
        raise RuntimeError("抽帧失败：没有得到任何图像。")
    listing = "\n".join(f"- {p}  （约 {dur * (i + 0.5) / len(fr):.1f}s）" for i, p in enumerate(fr))
    return (
        "你是视频分析执行器。任务：基于按时间顺序抽取的关键帧，分析一个视频。\n\n"
        f"原始视频：{path}\n总时长：{dur:.1f}s　抽帧数：{len(fr)}\n\n"
        "关键帧（按时间顺序）：\n"
        f"{listing}\n\n"
        "执行规则：\n"
        "1. 用 read_file 逐张读取上面的图片（每张都要看）。\n"
        "2. 只做只读分析，不要创建或修改任何文件，不要运行无关命令。\n\n"
        f"分析要求：\n{instruction}\n\n"
        "输出要求：结合帧间变化推断动作、流程与因果，不要只逐帧描述。结构化 Markdown，"
        "先给结论再给证据（时间点 + 画面）。不要输出思考过程。"
    )


# ---------------------------------------------------------------- tools
TOOLS = [
    {
        "name": "analyze_video",
        "description": (
            "用 Antigravity 内置的 Gemini Flash 模型分析本地视频（走 Google 订阅额度，无需 API Key）。"
            "同步等待结果。短视频可直接喂原视频（frames=0），长视频建议 frames=12~24 走抽帧模式。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "视频文件的绝对路径"},
                "instruction": {
                    "type": "string",
                    "description": "分析要求，例如：'概括剧情并标注时间点'、'找出所有出现的产品名'、'判断是否有异常行为'",
                    "default": "完整描述视频内容：场景、人物/物体、动作流程、关键时间点。",
                },
                "model": {
                    "type": "string",
                    "enum": ["flash", "flash_lite", "pro"],
                    "default": "flash",
                    "description": "模型档位。flash 最快，pro 推理更强",
                },
                "frames": {
                    "type": "integer",
                    "default": 0,
                    "description": "抽帧数量。0=直接喂原视频；长视频（>2分钟）建议 12~24",
                },
                "timeout": {"type": "number", "default": 900, "description": "等待超时（秒）"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "start_session",
        "description": "在 Antigravity 新建一个 agent 会话（异步，立即返回 conversation_id），用内置 Gemini 模型执行任意任务。适合并行编排。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "完整任务描述"},
                "model": {"type": "string", "enum": ["flash", "flash_lite", "pro"], "default": "flash"},
                "title": {"type": "string", "description": "会话标题（便于在 Antigravity 里辨认）"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "get_result",
        "description": "等待指定会话完成并返回最终回复。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "timeout": {"type": "number", "default": 900},
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "list_sessions",
        "description": "列出最近在 Antigravity 里创建的会话（含标题、最后更新时间）。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "health",
        "description": "检查 Antigravity 桥接是否可用（进程、端口、CSRF、可用模型档位）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def tool_health(_: dict) -> str:
    port, csrf = discover(force=True)
    info = {
        "ok": True,
        "ls_exe": str(LS_EXE),
        "ls_exe_exists": LS_EXE.exists(),
        "port": port,
        "csrf_found": bool(csrf),
        "models": ["flash_lite", "flash", "pro"],
        "antigravity_dir": str(AG_DIR),
    }
    return json.dumps(info, ensure_ascii=False, indent=2)


def tool_analyze_video(a: dict) -> str:
    path = a.get("path") or ""
    if not path:
        raise ValueError("path 必填")
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        raise FileNotFoundError(f"视频不存在: {p}")
    instruction = a.get("instruction") or "完整描述视频内容：场景、人物/物体、动作流程、关键时间点。"
    frames = int(a.get("frames") or 0)
    model = a.get("model") or "flash"
    timeout = float(a.get("timeout") or 900)

    t0 = time.time()
    prompt = build_video_prompt(str(p).replace("\\", "/"), instruction, frames)
    cid = start_session(prompt, model, title=f"视频分析: {p.name}")
    steps = wait_done(cid, timeout)
    res = summarize(cid, steps)
    res.update(
        {
            "ok": True,
            "mode": "frames" if frames > 0 else "native_video",
            "model": model,
            "elapsed_sec": round(time.time() - t0, 1),
            "video": str(p),
        }
    )
    log(f"analyze_video ok cid={cid} elapsed={res['elapsed_sec']}s")
    return json.dumps(res, ensure_ascii=False, indent=2)


def tool_start_session(a: dict) -> str:
    prompt = a.get("prompt") or ""
    if not prompt:
        raise ValueError("prompt 必填")
    cid = start_session(prompt, a.get("model") or "flash", a.get("title"))
    return json.dumps({"ok": True, "conversation_id": cid}, ensure_ascii=False)


def tool_get_result(a: dict) -> str:
    cid = a.get("conversation_id") or ""
    if not cid:
        raise ValueError("conversation_id 必填")
    steps = wait_done(cid, float(a.get("timeout") or 900))
    return json.dumps(summarize(cid, steps), ensure_ascii=False, indent=2)


def tool_list_sessions(a: dict) -> str:
    limit = int(a.get("limit") or 10)
    d = AG_DIR / "conversations"
    items = []
    if d.exists():
        files = sorted(d.glob("*.db"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
        for f in files:
            cid = f.stem
            title = ""
            tp = transcript_path(cid)
            if tp.exists():
                try:
                    first = tp.read_text(encoding="utf-8", errors="replace").splitlines()[0]
                    s = json.loads(first)
                    title = re.sub(r"<[^>]+>", " ", s.get("content") or "").strip()[:80]
                except Exception:
                    pass
            items.append(
                {
                    "conversation_id": cid,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime)),
                    "title_or_first_message": title,
                }
            )
    return json.dumps({"ok": True, "sessions": items}, ensure_ascii=False, indent=2)


HANDLERS = {
    "analyze_video": tool_analyze_video,
    "start_session": tool_start_session,
    "get_result": tool_get_result,
    "list_sessions": tool_list_sessions,
    "health": tool_health,
}


# ---------------------------------------------------------------- MCP stdio
def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> None:
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        send({
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "antigravity-bridge", "version": VERSION},
            },
        })
        return
    if method in ("notifications/initialized", "notifications/cancelled"):
        return
    if method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
        return
    if method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        return
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if not fn:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown tool {name}"}})
            return
        try:
            text = fn(args)
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": False}})
        except Exception as e:
            log(f"tool {name} error: {e}")
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}})
        return
    if mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})


def main() -> None:
    # Windows 下 sys.stdin/stdout 默认用系统 ANSI 代码页（GBK），
    # 会导致中文 prompt 在 JSON-RPC 传输中损坏（invalid UTF-8）。强制 UTF-8。
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    log(f"server start pid={os.getpid()}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        # 每条请求单独线程处理，避免长任务阻塞 initialize/ping
        if msg.get("method") == "tools/call":
            threading.Thread(target=handle, args=(msg,), daemon=True).start()
        else:
            handle(msg)


if __name__ == "__main__":
    main()
