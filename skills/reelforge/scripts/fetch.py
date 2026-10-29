"""下载参考视频（抖音/B站/小红书/YouTube/任意 yt-dlp 支持站点）。

    python fetch.py <url> [--out DIR] [--max-height 1080] [--force]
    python fetch.py --file D:\\clips\\a.mp4 --out work/a

产出（--out 目录内）：
    source.mp4    合并好音轨的成片
    source.info.json  yt-dlp 原始元数据（站点、标题、作者、发布时间）
    meta.json     归一化后的元数据 + ffprobe 结果
输出一行 JSON 到 stdout，其余日志走 stderr。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ffmpeg, now_iso, probe, read_json, run, slugify, write_json,
)

PLATFORMS = [
    ("douyin", r"douyin\.com/(?:video|note)/(\d+)"),
    ("douyin", r"v\.douyin\.com/(\w+)"),
    ("bilibili", r"bilibili\.com/video/(BV[0-9A-Za-z]+)"),
    ("bilibili", r"b23\.tv/(\w+)"),
    ("xiaohongshu", r"xiaohongshu\.com/(?:explore|discovery/item)/([0-9a-zA-Z]+)"),
    ("xiaohongshu", r"xhslink\.com/(\w+)"),
    ("youtube", r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([0-9A-Za-z_-]{11})"),
]


def parse_target(url: str) -> tuple[str, str]:
    for platform, pat in PLATFORMS:
        m = re.search(pat, url)
        if m:
            return platform, m.group(1)
    return "other", ""


def yt_dlp_base() -> list[str]:
    cli = shutil.which("yt-dlp")
    if cli:
        return [cli]
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        raise SystemExit("[env] 没装 yt-dlp：python -m pip install -U yt-dlp")
    return [sys.executable, "-m", "yt_dlp"]


def has_audio(path: Path) -> bool:
    return bool(probe(path).get("has_audio"))


def pick_video(out_dir: Path) -> Path | None:
    files = sorted(out_dir.glob("source*"))
    merged = [p for p in files if p.suffix.lower() == ".mp4" and not re.search(r"\.f\d+\.", p.name)]
    for p in merged:
        if has_audio(p):
            return p
    return merged[0] if merged else None


def merge_split_tracks(out_dir: Path) -> Path | None:
    """yt-dlp 找不到 ffmpeg 时会留下分离轨，这里兜底合并。"""
    v = a = None
    for p in out_dir.glob("source.f*"):
        if p.suffix.lower() in (".mp4", ".webm", ".mkv") and not has_audio(p):
            v = p
        elif p.suffix.lower() in (".m4a", ".mp3", ".aac", ".opus", ".webm"):
            a = p
    if not (v and a):
        return None
    out = out_dir / "source.mp4"
    run([ffmpeg(), "-v", "error", "-i", v, "-i", a, "-c", "copy", "-y", out], timeout=900)
    return out if out.exists() else None


def download(url: str, out_dir: Path, max_height: int, cookies: str | None, force: bool) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    existing = out_dir / "source.mp4"

    if existing.exists() and not force:
        meta = read_json(meta_path) if meta_path.exists() else {}
        meta.update(probe(existing))
        meta.setdefault("url", url)
        meta["reused"] = True
        write_json(meta_path, meta)
        return {"ok": True, "reused": True, **{k: str(v) for k, v in meta.items()}}

    ff_dir = str(ffmpeg().parent)
    cmd = yt_dlp_base() + [
        "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        "--merge-output-format", "mp4",
        "--ffmpeg-location", ff_dir,
        "--write-info-json", "--no-playlist", "--no-warnings",
        "--retries", "3", "--fragment-retries", "5",
        "-o", str(out_dir / "source.%(ext)s"),
        url,
    ]
    if cookies:
        cmd += ["--cookies-from-browser", cookies]

    env = {**os.environ, "PATH": ff_dir + os.pathsep + os.environ.get("PATH", "")}
    eprint(f"[fetch] yt-dlp → {out_dir}")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3600, env=env)
    if p.returncode != 0:
        return {
            "ok": False,
            "error": (p.stderr or p.stdout or "")[-1200:],
            "hint": "抖音/B站可能需要登录态：加 --cookies-from-browser chrome；"
                    "小红书需要完整链接（短链先展开）",
        }

    video = pick_video(out_dir)
    if video is None or not has_audio(video):
        video = merge_split_tracks(out_dir) or video
    if video is None:
        return {"ok": False, "error": "yt-dlp 跑完但没找到输出文件"}

    info = {}
    for f in out_dir.glob("source.info.json"):
        try:
            info = read_json(f)
            break
        except ValueError:
            pass

    meta = {
        "url": url,
        "platform": parse_target(url)[0],
        "video_id": parse_target(url)[1] or info.get("id"),
        "title": info.get("title") or "",
        "author": info.get("uploader") or info.get("channel") or "",
        "published_at": info.get("upload_date") or "",
        "source_page": info.get("webpage_url") or url,
        "fetched_at": now_iso(),
        "path": str(video),
        "reused": False,
        **probe(video),
    }
    write_json(meta_path, meta)
    return {"ok": True, "reused": False, "path": str(video), **meta}


def main() -> int:
    ap = argparse.ArgumentParser(description="下载参考视频到本地工作目录")
    ap.add_argument("url", nargs="?")
    ap.add_argument("--file", help="已有本地文件：只做探测与归一化，不下载")
    ap.add_argument("--out", help="输出目录，默认 work/<platform>_<id>")
    ap.add_argument("--max-height", type=int, default=1080)
    ap.add_argument("--cookies-from-browser", default=None,
                    help="chrome / edge / firefox，遇到登录墙时用")
    ap.add_argument("--force", action="store_true", help="已有 source.mp4 也重新下载")
    a = ap.parse_args()

    if a.file:
        src = Path(a.file).expanduser()
        if not src.exists():
            raise SystemExit(f"[fetch] 文件不存在: {src}")
        out = Path(a.out or f"work/{slugify(src.stem)}")
        out.mkdir(parents=True, exist_ok=True)
        dst = out / ("source" + src.suffix.lower())
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        meta = {"path": str(dst), "title": src.stem, "platform": "local",
                "reused": True, "fetched_at": now_iso(), **probe(dst)}
        write_json(out / "meta.json", meta)
        print(json.dumps({"ok": True, **meta}, ensure_ascii=False))
        return 0

    if not a.url:
        ap.error("需要 url 或 --file")

    platform, vid = parse_target(a.url)
    out = Path(a.out or f"work/{platform}_{vid or slugify(a.url)}")
    result = download(a.url, out, a.max_height, a.cookies_from_browser, a.force)
    result["out_dir"] = str(out)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
