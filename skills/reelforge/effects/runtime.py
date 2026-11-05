"""效果运行时：把效果库里的配方卡变成「真的能进片子的帧和片段」。

这是效果库与流水线之间唯一的接缝。任何项目（make.py / 别的 agent / 别的机器）
只要把本文件所在目录加进 sys.path，就能：

    import runtime
    img = runtime.render_frame("bar_grow", 1.2, 3.0, {"values": [20, 60, 90]})
    runtime.render_clip("bar_grow", 3.0, "out/bar.mp4", {"values": [20, 60, 90]})

目录解析顺序（换 agent 不丢库）：
  1. $REELFORGE_EFFECTS（若存在 fx/ 与 index.json）
  2. 随 skill 分发的 effects/（本文件旁边）
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image

SKILL_ROOT = Path(__file__).resolve().parent.parent
W, H = 1920, 1080


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    """ffmpeg 定位：环境变量 → PATH → 常见安装位置 → imageio_ffmpeg。

    换 agent / 换机器时 PATH 常常不含 ffmpeg（实测 WorkBuddy 会话里就丢了），
    只写 "ffmpeg" 会直接 FileNotFoundError，所以这里必须自己找。
    """
    import shutil
    p = os.environ.get("REELFORGE_FFMPEG")
    if p and Path(p).exists():
        return p
    w = shutil.which("ffmpeg")
    if w:
        return w
    for c in (Path.home() / ".local" / "bin" / "ffmpeg.exe",
              Path.home() / ".local" / "bin" / "ffmpeg",
              Path("C:/ffmpeg/bin/ffmpeg.exe"),
              Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe")):
        if c.exists():
            return str(c)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise FileNotFoundError("找不到 ffmpeg：设置 REELFORGE_FFMPEG=绝对路径，或把 ffmpeg 加进 PATH")


def local_root() -> Path:
    return Path(os.environ.get("REELFORGE_EFFECTS") or (Path.home() / ".reelforge" / "effects"))


def root() -> Path:
    p = local_root()
    if (p / "fx").is_dir() and (p / "index.json").exists():
        return p
    return Path(__file__).resolve().parent


def index_path() -> Path:
    return root() / "index.json"


def load_index() -> dict:
    """本地库 + 随仓库库合并，按 id 去重（仓库条目优先）。

    只认本地 index 会导致「仓库新增了效果，本机却看不见」；反过来只认仓库
    又会丢掉本机自己注册的效果。两边合并，才是真正的统一库。
    """
    p = index_path()
    bundled = SKILL_ROOT / "effects" / "index.json"
    if not p.exists():
        return json.loads(bundled.read_text(encoding="utf-8")) if bundled.exists() else {"items": []}
    idx = json.loads(p.read_text(encoding="utf-8"))
    if bundled.exists() and bundled.resolve() != p.resolve():
        b = json.loads(bundled.read_text(encoding="utf-8"))
        merged = {x["id"]: x for x in idx.get("items", [])}
        for x in b.get("items", []):
            merged[x["id"]] = x
        idx["items"] = list(merged.values())
        idx["version"] = b.get("version", idx.get("version"))
    return idx


def card(fx_id: str) -> dict | None:
    return next((x for x in load_index()["items"] if x["id"] == fx_id), None)


def ready_ids(kind: str | None = None) -> list[str]:
    out = []
    for x in load_index()["items"]:
        if x.get("status") != "ready" or not x.get("entry"):
            continue
        if kind and x.get("kind", "shot") != kind:
            continue
        out.append(x["id"])
    return out


def resolve_entry(entry: str) -> tuple[Path, str]:
    """模块解析：随仓库分发的版本优先，本地自定义模块作补充。

    这样同一 id 在任何 agent / 任何机器上跑出的画面一致；本地新注册的
    效果（仓库里没有同名文件）仍然可用。
    """
    part, _, fn = entry.partition(":")
    p = SKILL_ROOT / "effects" / part
    if not p.exists():
        p = root() / part
    return p, fn or "render"


@lru_cache(maxsize=64)
def get_render(fx_id: str):
    c = card(fx_id)
    if not c or not c.get("entry"):
        raise KeyError(f"效果未登记或不可运行：{fx_id}")
    path, fn = resolve_entry(c["entry"])
    if not path.exists():
        raise FileNotFoundError(f"效果模块缺失：{path}")
    for extra in (str(path.parent), str(path.parent.parent), str(root() / "fx")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    spec = importlib.util.spec_from_file_location(f"rfx_{fx_id}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, fn)


@lru_cache(maxsize=64)
def _still(path_str: str, at: float) -> Image.Image:
    """图片直接读；视频用 ffmpeg 抽一帧。结果按 (路径, 时间) 缓存。"""
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"素材不存在：{p}")
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return Image.open(p).convert("RGB")
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", f"{at:.3f}",
           "-i", str(p), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode or not r.stdout:
        raise RuntimeError(f"抽帧失败：{p} @ {at:.2f}s\n{r.stderr.decode('utf-8', 'replace')[-600:]}")
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def prepare(params: dict | None) -> dict:
    """转场类：把 a/b（图片或视频路径）解析成 a_img/b_img，供纯函数使用。"""
    p = dict(params or {})
    for side in ("a", "b"):
        if p.get(f"{side}_img") is not None or not p.get(side):
            continue
        p[f"{side}_img"] = _still(str(p[side]), float(p.get(f"{side}_at", 0.0)))
    return p


def render_frame(fx_id: str, t: float, total: float, params: dict | None = None) -> Image.Image:
    """渲染单帧。t 是本镜内相对秒数。"""
    p = prepare(params)
    img = get_render(fx_id)(float(t), float(total), p)
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    return img.convert("RGB")


def render_clip(fx_id: str, duration: float, out: str | Path,
                params: dict | None = None, fps: int = 30, force: bool = False) -> Path:
    """把效果渲染成一段无声 mp4（逐帧 rawvideo 管道 → libx264）。

    已有文件且大小正常时默认跳过；改了效果代码要 force=True 或删文件。
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 20000 and not force:
        return out
    p = prepare(params)
    fn = get_render(fx_id)
    n = max(1, int(round(float(duration) * fps)))
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
           "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    try:
        for i in range(n):
            img = fn(i / fps, float(duration), p)
            if img.size != (W, H):
                img = img.resize((W, H), Image.LANCZOS)
            proc.stdin.write(img.convert("RGB").tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg 渲染失败：{fx_id}\n{err[-900:]}")
    except Exception:
        proc.kill()
        raise
    return out


def self_check(at: float = 0.9, total: float = 3.0) -> dict:
    """所有 ready 效果各渲一帧，返回 {id: OK/错误}。用于提交前回归。"""
    import tempfile
    result = {}
    probe = Path(tempfile.gettempdir()) / "rf_self_check_probe.png"
    if not probe.exists():
        Image.new("RGB", (W, H), (226, 219, 200)).save(probe)
    for fx in ready_ids():
        c = card(fx) or {}
        p = {}
        if "image" in (c.get("requires") or []):
            p["image"] = str(probe)
        if c.get("kind") == "transition":
            pat, ptot = 0.30, 0.60          # 转场要看中间态，不能取终态
        else:
            pat, ptot = at, total
        try:
            img = render_frame(fx, pat, ptot, p)
            result[fx] = "OK" if img.size == (W, H) else f"尺寸异常 {img.size}"
        except Exception as e:
            result[fx] = f"{type(e).__name__}: {e}"
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ReelForge 效果运行时")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=lambda a: print(json.dumps(self_check(), ensure_ascii=False, indent=1)))
    p = sub.add_parser("clip")
    p.add_argument("fx")
    p.add_argument("--dur", type=float, default=3.0)
    p.add_argument("--out", required=True)
    p.add_argument("--params", default="{}")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=lambda a: print(render_clip(a.fx, a.dur, a.out, json.loads(a.params), a.fps, a.force)))
    p = sub.add_parser("frame")
    p.add_argument("fx")
    p.add_argument("--at", type=float, default=1.2)
    p.add_argument("--total", type=float, default=3.0)
    p.add_argument("--out", required=True)
    p.add_argument("--params", default="{}")
    p.set_defaults(fn=lambda a: render_frame(a.fx, a.at, a.total, json.loads(a.params)).save(a.out))
    a = ap.parse_args()
    a.fn(a)
