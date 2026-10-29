"""video-factory 公共工具：ffmpeg 定位、探测、JSON 读写、CUDA DLL 注册。

设计原则：不依赖任何旧流水线模块，所有路径都能通过环境变量覆盖，
便于把 skill 整体搬到别的机器或给别人用。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
VENDOR = SKILL_DIR / "vendor"


def _candidates(name: str) -> list[Path]:
    exe = f"{name}.exe" if os.name == "nt" else name
    cands: list[Path] = []
    env = os.environ.get(f"VF_{name.upper()}")
    if env:
        cands.append(Path(env))
    which = shutil.which(name)
    if which:
        cands.append(Path(which))
    cands += [
        VENDOR / "ffmpeg" / "bin" / exe,
        VENDOR / "ffmpeg" / exe,
    ]
    return cands


def find_bin(name: str) -> Path:
    for p in _candidates(name):
        if p.exists():
            return p
    raise SystemExit(
        f"[env] 找不到 {name}。装一个，或用 VF_{name.upper()} 指定完整路径。\n"
        f"      Windows: winget install Gyan.FFmpeg"
    )


def ffmpeg() -> Path:
    return find_bin("ffmpeg")


def ffprobe() -> Path:
    return find_bin("ffprobe")


def run(cmd: list[str | Path], timeout: int = 1800, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    if check and p.returncode != 0:
        raise RuntimeError(
            f"命令失败 rc={p.returncode}: {' '.join(str(c) for c in cmd)[:300]}\n"
            f"{(p.stderr or p.stdout or '')[:800]}"
        )
    return p


def probe(path: str | Path) -> dict:
    """用 ffprobe 取时长/分辨率/帧率/音轨。失败返回空 dict，不抛。"""
    path = Path(path)
    if not path.exists():
        return {}
    p = run([
        ffprobe(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ], timeout=120, check=False)
    if p.returncode != 0:
        return {}
    try:
        d = json.loads(p.stdout or "{}")
    except ValueError:
        return {}

    fmt = d.get("format") or {}
    v = next((s for s in d.get("streams") or [] if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams") or [] if s.get("codec_type") == "audio"), {})
    num, _, den = (v.get("avg_frame_rate") or "0/1").partition("/")
    try:
        fps = round(float(num) / float(den), 3) if float(den or 0) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        "duration_sec": round(float(fmt.get("duration") or 0), 2),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": fps,
        "video_codec": v.get("codec_name"),
        "audio_codec": a.get("codec_name"),
        "has_audio": bool(a),
        "bytes": int(fmt.get("size") or 0),
    }


def slugify(text: str, fallback: str = "clip") -> str:
    text = (text or "").strip()
    text = re.sub(r"[\\/:*?\"<>|\s]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    text = text[:48]
    return text or fallback


def write_json(path: str | Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hhmmss(sec: float) -> str:
    sec = max(0.0, float(sec or 0))
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


_DLL_HANDLES: list = []


def setup_cuda_dlls(verbose: bool = False) -> list[str]:
    """把 pip 装的 NVIDIA 运行库加进 DLL 搜索路径。

    ctranslate2 的 wheel 不带 CUDA 运行时，需要 cublas64_12.dll / cudnn 系列，
    它们由 nvidia-cublas-cu12 / nvidia-cudnn-cu12 提供，落在
    site-packages/nvidia/<pkg>/bin，但不在系统 PATH 里。
    add_dll_directory 的句柄不能被 GC 回收，否则目录立即失效。
    """
    if os.name != "nt":
        return []
    import site

    found: list[str] = []
    roots: list[str] = []
    for getter in ("getsitepackages", "getusersitepackages"):
        try:
            v = getattr(site, getter)()
        except AttributeError:
            continue
        roots += v if isinstance(v, list) else [v]

    for sp in dict.fromkeys(roots):
        nv = Path(sp) / "nvidia"
        if not nv.is_dir():
            continue
        for pkg in sorted(nv.iterdir()):
            for sub in ("bin", "lib"):
                p = pkg / sub
                if not p.is_dir():
                    continue
                try:
                    _DLL_HANDLES.append(os.add_dll_directory(str(p)))
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
                found.append(str(p))
    if verbose:
        print(f"[cuda] 注册 {len(found)} 个 DLL 目录")
    return found


def decode_16k_mono(src: str | Path, dst: str | Path | None = None) -> Path:
    """解码成 16kHz 单声道 WAV。

    不用 faster-whisper 自带的 decode_audio：它走 PyAV，而 av 19 删掉了
    open() 的 metadata_errors 参数，faster-whisper 1.2.1 还在传，直接 TypeError。
    """
    src = Path(src)
    dst = Path(dst) if dst else src.with_name(f"_asr_{os.getpid()}.wav")
    run([
        ffmpeg(), "-v", "error", "-i", src,
        "-ar", "16000", "-ac", "1", "-f", "wav",
        "-acodec", "pcm_s16le", "-y", dst,
    ])
    return dst


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def eprint(*args):
    print(*args, file=sys.stderr)
