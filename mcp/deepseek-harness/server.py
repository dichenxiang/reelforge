#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP Server: deepseek-harness-bridge
把本机安装的 DeepSeek Harness（dsh）暴露成 MCP 工具，供上层 Agent 调用。

原理：直接以 node 模式启动 DeepSeek Harness.exe，跑 dsh 的 headless profile，
复用桌面端已登录的 deepseek-account 账号额度（不需要 DEEPSEEK_API_KEY），
读 stdout 上的 NDJSON run 事件拿最终回答与工具调用轨迹。

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

VERSION = "1.0.0"

TOOL_DIR = Path(__file__).resolve().parent
PATCH_DIR = TOOL_DIR / "patches"
INDEX_FILE = TOOL_DIR / "sessions.json"
INSTALL_CACHE = TOOL_DIR / "install.json"

DSH_HOME = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
CLI_REL = (
    Path("resources") / "app.asar" / "dsh" / "node_modules"
    / "@deepseek-ai" / "dsh-desktop-host" / "lib" / "cli.js"
)

MODELS = ["deepseek-v4.1-flash", "deepseek-flash", "deepseek-v4-pro"]
DEFAULT_MODEL = "deepseek-v4.1-flash"
DEFAULT_EFFORT = "max"

# ---------------------------------------------------------------- logging
LOG_PATH = Path(os.environ.get("TEMP", tempfile.gettempdir())) / "dsh_mcp.log"


def log(msg: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------- discovery
_install_cache: dict = {"ts": 0.0, "exe": None, "cli": None}


def _candidates() -> list[Path]:
    out: list[Path] = []
    env_exe = os.environ.get("DSH_EXE")
    if env_exe:
        out.append(Path(env_exe))
    if INSTALL_CACHE.exists():
        try:
            data = json.loads(INSTALL_CACHE.read_text(encoding="utf-8"))
            if data.get("exe"):
                out.append(Path(data["exe"]))
        except Exception:
            pass
    out += [
        Path(r"E:\Deepseek Herness\DeepSeek Harness.exe"),
        Path(r"D:\Deepseek Herness\DeepSeek Harness.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DeepSeek Harness" / "DeepSeek Harness.exe",
        Path(r"C:\Program Files\DeepSeek Harness\DeepSeek Harness.exe"),
    ]
    # 盘符扫描：安装在任意盘根目录 / Program Files 下也能找到
    for letter in "CDEFGH":
        out.append(Path(f"{letter}:\\Deepseek Herness\\DeepSeek Harness.exe"))
        out.append(Path(f"{letter}:\\DeepSeek Harness\\DeepSeek Harness.exe"))
        out.append(Path(f"{letter}:\\Program Files\\DeepSeek Harness\\DeepSeek Harness.exe"))
    return [p for p in out if str(p).strip() and ":" in str(p)]


def _asar_has_cli(asar: Path) -> bool:
    """app.asar 里的 cli.js 在磁盘上不存在（asar 是打包文件），
    所以直接读 asar 头部的目录 JSON 校验布局，而不是 is_file()。"""
    try:
        with asar.open("rb") as f:
            head = f.read(4 * 1024 * 1024).decode("utf-8", "ignore")
        i = head.find('"dsh-desktop-host":{"files"')
        if i < 0:
            return False
        return '"cli.js"' in head[i:i + 8000] and '"lib"' in head[i:i + 8000]
    except Exception as e:
        log(f"asar probe fail: {e}")
        return False


def _from_running() -> list[Path]:
    """从正在运行的桌面端进程拿 exe 路径。"""
    try:
        r = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='DeepSeek Harness.exe'\" "
                "| Select-Object -First 1 -ExpandProperty ExecutablePath",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
        )
        p = (r.stdout or "").strip().splitlines()
        return [Path(p[0].strip())] if p and p[0].strip() else []
    except Exception:
        return []


def discover(force: bool = False) -> tuple[Path, Path]:
    now = time.time()
    if not force and _install_cache["exe"] and now - _install_cache["ts"] < 60:
        return _install_cache["exe"], _install_cache["cli"]

    tried: list[str] = []
    seen: set[str] = set()
    for exe in _candidates() + _from_running():
        key = str(exe).lower()
        if key in seen:
            continue
        seen.add(key)
        tried.append(str(exe))
        if not exe.is_file():
            continue
        asar = exe.parent / "resources" / "app.asar"
        if not asar.is_file():
            log(f"app.asar missing under {exe.parent}")
            continue
        if not _asar_has_cli(asar):
            log(f"dsh-desktop-host/lib/cli.js not in {asar}")
            continue
        cli = exe.parent / CLI_REL
        _install_cache.update({"ts": now, "exe": exe, "cli": cli})
        try:
            INSTALL_CACHE.write_text(
                json.dumps({"exe": str(exe)}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        return exe, cli

    raise RuntimeError(
        "找不到可用的 DeepSeek Harness 安装。请确认已安装并至少启动过一次桌面端，"
        "或用环境变量 DSH_EXE 指定 'DeepSeek Harness.exe' 的完整路径。已尝试: "
        + "; ".join(tried[:8])
    )


# ---------------------------------------------------------------- patch
_yaml_bad = re.compile(r"[^A-Za-z0-9._-]")


def patch_for(model: str, effort: str) -> Path:
    """生成/复用 profile 补丁：开账号登录、指定模型档位。"""
    model = (model or DEFAULT_MODEL).strip()
    effort = (effort or DEFAULT_EFFORT).strip()
    if _yaml_bad.search(model) or _yaml_bad.search(effort):
        raise ValueError(f"model / reasoning_effort 含非法字符: {model!r} {effort!r}")
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    p = PATCH_DIR / f"account_{model}_{effort}.yml"
    body = (
        "# 由 WorkBuddy deepseek-harness MCP 自动生成：\n"
        "# headless profile 默认要求 DEEPSEEK_API_KEY，这里改成复用桌面端账号登录。\n"
        "- id: deepseek-account\n"
        "  disabled: false\n"
        "- id: credentials\n"
        "  disabled: false\n"
        "- id: authorization\n"
        "  disabled: false\n"
        "- id: agent-default-model\n"
        '  name: "@deepseek-ai/dsh-agent-default-model"\n'
        "  config:\n"
        "    provider: deepseek-account\n"
        f"    model: {model}\n"
        f"    reasoningEffort: {effort}\n"
    )
    if not p.exists() or p.read_text(encoding="utf-8") != body:
        p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------- run engine
def default_cwd() -> Path:
    """MCP 启动时的 cwd 一般是当前工作区；若落在工具目录/系统目录，则退到 dsh 默认工作区。"""
    bad_prefixes = [
        str(TOOL_DIR).lower(),
        os.environ.get("WINDIR", r"C:\Windows").lower(),
        os.environ.get("PROGRAMFILES", r"C:\Program Files").lower(),
        str(Path.home() / "AppData").lower(),
    ]
    for cand in [os.environ.get("DSH_MCP_CWD"), os.getcwd()]:
        if not cand:
            continue
        p = Path(cand)
        if not p.is_dir():
            continue
        if any(str(p).lower().startswith(b) for b in bad_prefixes):
            continue
        return p
    fallback = Path.home() / "Documents" / "deepseek-harness" / "default-workspace"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def resolve_cwd(cwd: str | None) -> Path:
    if not cwd:
        return default_cwd()
    p = Path(str(cwd)).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.is_dir():
        raise FileNotFoundError(f"工作目录不存在: {p}")
    return p


_CREATE_NO_WINDOW = 0x08000000
_NEW_GROUP = 0x00000200


def _kill_tree(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, text=True, timeout=20,
            creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def summarize(events: list[dict], stdout_tail: list[str], stderr_text: str, rc: int, elapsed: float) -> dict:
    sid = None
    final = ""
    texts: list[str] = []
    thinking_len = 0
    tools: list[dict] = []
    usage = {"input": 0, "output": 0, "cache_read": 0, "total": 0}
    steps = 0
    err = None

    for ev in events:
        t = ev.get("type")
        if t == "session":
            sid = ev.get("sessionId") or sid
        elif t == "thinking":
            thinking_len += len(ev.get("text") or "")
        elif t == "text":
            if ev.get("text"):
                texts.append(ev["text"])
        elif t == "tool_call":
            inp = ev.get("input")
            try:
                brief = json.dumps(inp, ensure_ascii=False)
            except Exception:
                brief = str(inp)
            tools.append(
                {
                    "tool": ev.get("tool"),
                    "input": brief[:400] + ("…" if len(brief) > 400 else ""),
                }
            )
        elif t == "status":
            if ev.get("phase") == "step_end":
                steps += 1
                u = ev.get("usage") or {}
                usage["input"] += int(u.get("inputTokens") or 0)
                usage["output"] += int(u.get("outputTokens") or 0)
                usage["cache_read"] += int(u.get("cacheReadTokens") or 0)
                usage["total"] += int(u.get("totalTokens") or 0)
            elif ev.get("phase") == "turn_end":
                reason = ev.get("reason") or {}
                if reason.get("kind") == "error":
                    e = reason.get("error") or {}
                    err = e.get("message") or e.get("code") or "模型返回错误"
        elif t == "final":
            if ev.get("text"):
                final = ev["text"]

    # 非 JSON 行里 dsh 会打印真正的失败原因（例如 MISSING_CREDENTIAL）
    for line in stdout_tail:
        if line.startswith("dsh:"):
            err = err or line[4:].strip()
    if not err:
        for line in (stderr_text or "").splitlines():
            if line.startswith("dsh:"):
                err = line[4:].strip()

    if not final:
        final = "\n".join(t for t in texts if t).strip()

    return {
        "ok": bool(final) and not err,
        "answer": final,
        "session_id": sid,
        "error": err,
        "tool_calls": tools,
        "steps": steps,
        "usage": usage,
        "reasoning_chars": thinking_len,
        "elapsed_sec": round(elapsed, 1),
        "exit_code": rc,
    }


def run_task(
    task: str,
    cwd: Path,
    model: str,
    effort: str,
    timeout: float,
    session_id: str | None = None,
) -> dict:
    exe, cli = discover()
    patch = patch_for(model, effort)
    argv = [str(exe), "--expose-internals", str(cli), "headless", "--patch", str(patch), "--json"]
    if session_id:
        argv += ["--session-id", session_id]
    argv.append("-")  # 任务从 stdin 读，避免超长/引号问题

    env = os.environ.copy()
    env["ELECTRON_RUN_AS_NODE"] = "1"
    env.setdefault("DSH_HOME", str(DSH_HOME))
    env.setdefault("PYTHONIOENCODING", "utf-8")

    t0 = time.time()
    log(f"run model={model} effort={effort} cwd={cwd} sid={session_id} len={len(task)}")
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=(_CREATE_NO_WINDOW | _NEW_GROUP) if os.name == "nt" else 0,
        )
    except Exception as e:
        raise RuntimeError(f"启动 DeepSeek Harness 失败: {e}")

    events: list[dict] = []
    stdout_tail: list[str] = []
    stderr_buf: list[str] = []

    def feed() -> None:
        try:
            proc.stdin.write(task)  # type: ignore[union-attr]
            proc.stdin.flush()  # type: ignore[union-attr]
        except Exception as e:
            log(f"stdin write fail: {e}")
        finally:
            try:
                proc.stdin.close()  # type: ignore[union-attr]
            except Exception:
                pass

    def read_out() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\r\n")
                if not line.strip():
                    continue
                if line.lstrip().startswith("{"):
                    try:
                        ev = json.loads(line)
                        events.append(ev)
                        continue
                    except Exception:
                        pass
                stdout_tail.append(line)
                if len(stdout_tail) > 200:
                    del stdout_tail[:100]
        except Exception as e:
            log(f"read stdout fail: {e}")

    def read_err() -> None:
        try:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_buf.append(line)
                if len(stderr_buf) > 400:
                    del stderr_buf[:200]
        except Exception:
            pass

    threads = [
        threading.Thread(target=feed, daemon=True),
        threading.Thread(target=read_out, daemon=True),
        threading.Thread(target=read_err, daemon=True),
    ]
    for th in threads:
        th.start()

    timed_out = False
    while True:
        if proc.poll() is not None:
            break
        if time.time() - t0 > timeout:
            timed_out = True
            log(f"timeout {timeout}s, kill {proc.pid}")
            _kill_tree(proc.pid)
            try:
                proc.wait(timeout=15)
            except Exception:
                pass
            break
        time.sleep(0.2)

    for th in threads:
        th.join(timeout=5)
    rc = proc.returncode if proc.returncode is not None else -1
    res = summarize(events, stdout_tail, "".join(stderr_buf), rc, time.time() - t0)
    if timed_out:
        res["ok"] = False
        res["error"] = res.get("error") or f"超时（{timeout:.0f}s），已终止进程；任务可能在 Harness 侧未完成"
    res["model"] = model
    res["reasoning_effort"] = effort
    res["cwd"] = str(cwd)
    log(f"done ok={res['ok']} sid={res['session_id']} elapsed={res['elapsed_sec']}")
    return res


# ---------------------------------------------------------------- session index
_index_lock = threading.Lock()


def index_append(res: dict, task: str) -> None:
    sid = res.get("session_id")
    if not sid:
        return
    entry = {
        "session_id": sid,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cwd": res.get("cwd"),
        "model": res.get("model"),
        "task": (task or "").strip().replace("\n", " ")[:160],
        "answer": (res.get("answer") or "").strip().replace("\n", " ")[:160],
        "ok": res.get("ok"),
    }
    with _index_lock:
        data: list[dict] = []
        if INDEX_FILE.exists():
            try:
                data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = []
        data = [d for d in data if d.get("session_id") != sid]
        data.insert(0, entry)
        try:
            INDEX_FILE.write_text(
                json.dumps(data[:300], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            log(f"index write fail: {e}")


def _key_to_cwd(key: str) -> str:
    """--C-Users-foo-Bar-- → C:\\Users\\foo\\Bar"""
    parts = [p for p in key.strip("-").split("-") if p]
    if len(parts) >= 2:
        return parts[0] + ":\\" + "\\".join(parts[1:])
    return key


def scan_sessions(limit: int) -> list[dict]:
    root = DSH_HOME / "sessions"
    out: list[dict] = []
    if not root.is_dir():
        return out
    try:
        for ws in root.iterdir():
            if not ws.is_dir():
                continue
            for sd in ws.iterdir():
                if not sd.is_dir() or not sd.name.startswith("session-"):
                    continue
                f = sd / "session.v4.jsonl.zstd"
                mtime = f.stat().st_mtime if f.exists() else sd.stat().st_mtime
                out.append(
                    {
                        "session_id": sd.name,
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                        "workspace_key": ws.name,
                        "cwd": _key_to_cwd(ws.name),
                        "_mtime": mtime,
                    }
                )
    except Exception as e:
        log(f"scan fail: {e}")
    out.sort(key=lambda x: x["_mtime"], reverse=True)
    return out[: max(limit * 3, 30)]


# ---------------------------------------------------------------- jobs (async)
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def job_start(task: str, cwd: Path, model: str, effort: str, timeout: float) -> str:
    jid = "job-" + uuid.uuid4().hex[:12]
    slot = {
        "job_id": jid,
        "status": "running",
        "task": task[:160],
        "cwd": str(cwd),
        "model": model,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "result": None,
        "error": None,
        "event": threading.Event(),
    }
    with JOBS_LOCK:
        JOBS[jid] = slot

    def worker() -> None:
        try:
            res = run_task(task, cwd, model, effort, timeout)
            slot["result"] = res
            slot["status"] = "done" if res.get("ok") else "failed"
            index_append(res, task)
        except Exception as e:
            slot["error"] = str(e)
            slot["status"] = "failed"
        finally:
            slot["event"].set()

    threading.Thread(target=worker, daemon=True).start()
    return jid


# ---------------------------------------------------------------- tools
TOOLS = [
    {
        "name": "run",
        "description": (
            "调用本机 DeepSeek Harness（dsh）跑一个任务，同步返回最终回答。"
            "底层是 dsh 的 headless agent：它会真实读写文件、执行命令（相当于在 cwd 里开了一个编码 agent）。"
            "适合：让 DeepSeek 独立完成一段分析/编码/批处理，或把大任务外包出去。"
            "走桌面端已登录的账号额度，不需要 API Key。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "完整任务描述（可多行，越具体越好）"},
                "cwd": {"type": "string", "description": "工作目录绝对路径，默认当前工作区"},
                "model": {
                    "type": "string",
                    "enum": MODELS,
                    "default": DEFAULT_MODEL,
                    "description": "deepseek-flash 快；deepseek-v4-pro 更强",
                },
                "reasoning_effort": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "max"],
                    "default": DEFAULT_EFFORT,
                    "description": "思考强度，越高越慢越稳",
                },
                "session_id": {"type": "string", "description": "在已有会话上继续（不填=新会话）"},
                "timeout": {"type": "number", "default": 900, "description": "等待超时（秒）"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "start",
        "description": "异步启动一个 dsh 任务，立刻返回 job_id（可并行跑多个），之后用 result 取结果。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "cwd": {"type": "string"},
                "model": {"type": "string", "enum": MODELS, "default": DEFAULT_MODEL},
                "reasoning_effort": {
                    "type": "string", "enum": ["low", "medium", "high", "max"], "default": DEFAULT_EFFORT,
                },
                "timeout": {"type": "number", "default": 1800},
            },
            "required": ["task"],
        },
    },
    {
        "name": "result",
        "description": "等待 start 启动的任务完成并返回结果；不传 job_id 则列出所有任务状态。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "timeout": {"type": "number", "default": 900, "description": "本次最多等待秒数"},
            },
        },
    },
    {
        "name": "continue_session",
        "description": "在已有 dsh 会话上追加一轮对话（保留上下文），返回新的回答。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "task": {"type": "string", "description": "这一轮要说什么/做什么"},
                "cwd": {"type": "string", "description": "该会话原本的工作目录（不填则自动从索引推断）"},
                "model": {"type": "string", "enum": MODELS, "default": DEFAULT_MODEL},
                "reasoning_effort": {
                    "type": "string", "enum": ["low", "medium", "high", "max"], "default": DEFAULT_EFFORT,
                },
                "timeout": {"type": "number", "default": 900},
            },
            "required": ["session_id", "task"],
        },
    },
    {
        "name": "sessions",
        "description": "列出最近的 dsh 会话（含首条任务摘要、工作目录、时间）。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "health",
        "description": "自检桥接是否可用：安装路径、cli.js、profile 补丁、账号凭据、可用模型。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "probe": {"type": "boolean", "default": False, "description": "额外跑一次最小任务验证端到端（约 5 秒）"},
            },
        },
    },
]


def _fmt(res: dict) -> str:
    return json.dumps(res, ensure_ascii=False, indent=2)


def tool_run(a: dict) -> str:
    task = (a.get("task") or "").strip()
    if not task:
        raise ValueError("task 必填")
    cwd = resolve_cwd(a.get("cwd"))
    res = run_task(
        task,
        cwd,
        a.get("model") or DEFAULT_MODEL,
        a.get("reasoning_effort") or DEFAULT_EFFORT,
        float(a.get("timeout") or 900),
        a.get("session_id") or None,
    )
    index_append(res, task)
    return _fmt(res)


def tool_start(a: dict) -> str:
    task = (a.get("task") or "").strip()
    if not task:
        raise ValueError("task 必填")
    jid = job_start(
        task,
        resolve_cwd(a.get("cwd")),
        a.get("model") or DEFAULT_MODEL,
        a.get("reasoning_effort") or DEFAULT_EFFORT,
        float(a.get("timeout") or 1800),
    )
    return json.dumps({"ok": True, "job_id": jid}, ensure_ascii=False)


def tool_result(a: dict) -> str:
    jid = a.get("job_id")
    if not jid:
        with JOBS_LOCK:
            rows = [
                {
                    "job_id": j["job_id"],
                    "status": j["status"],
                    "model": j["model"],
                    "started_at": j["started_at"],
                    "task": j["task"],
                }
                for j in JOBS.values()
            ]
        return json.dumps({"ok": True, "jobs": rows}, ensure_ascii=False, indent=2)
    slot = JOBS.get(str(jid))
    if not slot:
        raise ValueError(f"未知 job_id: {jid}")
    wait = float(a.get("timeout") or 900)
    slot["event"].wait(timeout=wait)
    if slot["status"] == "running":
        return json.dumps(
            {"ok": True, "status": "running", "job_id": jid, "hint": "还没跑完，稍后再取一次"},
            ensure_ascii=False,
        )
    if slot.get("result"):
        return _fmt(slot["result"])
    return json.dumps(
        {"ok": False, "status": slot["status"], "job_id": jid, "error": slot.get("error")},
        ensure_ascii=False, indent=2,
    )


def tool_continue(a: dict) -> str:
    sid = (a.get("session_id") or "").strip()
    task = (a.get("task") or "").strip()
    if not sid or not task:
        raise ValueError("session_id 与 task 必填")
    cwd_arg = a.get("cwd")
    if not cwd_arg and INDEX_FILE.exists():
        try:
            for d in json.loads(INDEX_FILE.read_text(encoding="utf-8")):
                if d.get("session_id") == sid and d.get("cwd"):
                    cwd_arg = d["cwd"]
                    break
        except Exception:
            pass
    res = run_task(
        task,
        resolve_cwd(cwd_arg),
        a.get("model") or DEFAULT_MODEL,
        a.get("reasoning_effort") or DEFAULT_EFFORT,
        float(a.get("timeout") or 900),
        session_id=sid,
    )
    index_append(res, task)
    return _fmt(res)


def tool_sessions(a: dict) -> str:
    limit = int(a.get("limit") or 10)
    titles: dict[str, dict] = {}
    if INDEX_FILE.exists():
        try:
            for d in json.loads(INDEX_FILE.read_text(encoding="utf-8")):
                titles[d.get("session_id")] = d
        except Exception:
            pass
    rows = []
    seen = set()
    for s in scan_sessions(limit):
        sid = s["session_id"]
        seen.add(sid)
        meta = titles.get(sid) or {}
        rows.append(
            {
                "session_id": sid,
                "updated_at": s["updated_at"],
                "cwd": meta.get("cwd") or s.get("cwd"),
                "task": meta.get("task") or "",
                "model": meta.get("model") or "",
            }
        )
    for sid, meta in titles.items():
        if sid in seen:
            continue
        rows.append(
            {
                "session_id": sid,
                "updated_at": meta.get("at"),
                "cwd": meta.get("cwd"),
                "task": meta.get("task"),
                "model": meta.get("model"),
            }
        )
    return json.dumps({"ok": True, "sessions": rows[:limit]}, ensure_ascii=False, indent=2)


def tool_health(a: dict) -> str:
    info: dict = {"ok": False, "models": MODELS, "dsh_home": str(DSH_HOME)}
    try:
        exe, cli = discover(force=True)
        asar = exe.parent / "resources" / "app.asar"
        info.update(
            {
                "exe": str(exe),
                "cli_js": str(cli),
                "app_asar": str(asar),
                "cli_js_in_asar": _asar_has_cli(asar),
                "installed": True,
            }
        )
    except Exception as e:
        info["error"] = str(e)
        info["ok"] = False
        return json.dumps(info, ensure_ascii=False, indent=2)

    try:
        p = patch_for(DEFAULT_MODEL, DEFAULT_EFFORT)
        info["patch"] = str(p)
        info["patch_ok"] = p.is_file()
    except Exception as e:
        info["patch_error"] = str(e)

    cred = DSH_HOME / ".credentials.yaml"
    info["credentials_file"] = str(cred)
    if cred.exists():
        txt = cred.read_text(encoding="utf-8", errors="replace")
        info["account_logged_in"] = "deepseek-account-platform" in txt
    else:
        info["account_logged_in"] = False

    info["default_cwd"] = str(default_cwd())

    if a.get("probe"):
        try:
            res = run_task("只输出 OK 两个字母，不要任何解释。", default_cwd(), DEFAULT_MODEL, "low", 180)
            info["probe"] = {"ok": res.get("ok"), "answer": res.get("answer"), "error": res.get("error"),
                             "elapsed_sec": res.get("elapsed_sec")}
            info["ok"] = bool(res.get("ok"))
        except Exception as e:
            info["probe"] = {"ok": False, "error": str(e)}
    else:
        info["ok"] = bool(info.get("cli_js_in_asar") and info.get("account_logged_in"))
    return json.dumps(info, ensure_ascii=False, indent=2)


HANDLERS = {
    "run": tool_run,
    "start": tool_start,
    "result": tool_result,
    "continue_session": tool_continue,
    "sessions": tool_sessions,
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
                "serverInfo": {"name": "deepseek-harness-bridge", "version": VERSION},
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
            ok = True
            try:
                ok = json.loads(text).get("ok", True) is not False
            except Exception:
                pass
            send({
                "jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": text}], "isError": not ok},
            })
        except Exception as e:
            log(f"tool {name} error: {e}")
            send({
                "jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True},
            })
        return
    if mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    log(f"server start pid={os.getpid()} cwd={os.getcwd()}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("method") == "tools/call":
            threading.Thread(target=handle, args=(msg,), daemon=True).start()
        else:
            handle(msg)


if __name__ == "__main__":
    main()
