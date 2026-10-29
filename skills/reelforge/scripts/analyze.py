"""把一条视频变成可拆解的「证据包」：转写 + 镜头切点 + 抽帧 + 联系表。

    python analyze.py --url https://... --out work/xxx
    python analyze.py --video work/xxx/source.mp4 --frames 24 --lang zh

产出（--out 目录内）：
    transcript.json  逐句时间戳（faster-whisper large-v3-turbo / CUDA）
    frames/          f01_0.8s.jpg … 均匀抽帧
    contact_sheet.jpg  带时间戳的联系表，给人或视觉模型看全貌
    evidence.json    结构化证据（机器读）
    evidence.md      同一份证据的可读版（编排层读这个做拆解）
    clips/           --clips N 时额外切出的连续片段，用于判断运镜/动效
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    decode_16k_mono, ffmpeg, hhmmss, now_iso, probe, read_json, run,
    setup_cuda_dlls, write_json,
)


# ---------------------------------------------------------------- 转写

def transcribe(video: Path, out_json: Path, model_size: str, device: str,
               compute: str, lang: str, words: bool) -> dict:
    if out_json.exists():
        old = read_json(out_json)
        if old.get("segments"):
            print(f"[asr] 复用已有转写 {out_json}", file=sys.stderr)
            return old

    setup_cuda_dlls()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("[env] 没装 faster-whisper：python -m pip install faster-whisper")

    try:
        model = WhisperModel(model_size, device=device, compute_type=compute)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            f"[asr] 模型加载失败 device={device} compute={compute}: {e}\n"
            f"      GPU 需要 nvidia-cublas-cu12 + nvidia-cudnn-cu12；"
            f"实在不行显式传 --device cpu --compute int8"
        ) from e

    wav = decode_16k_mono(video)
    try:
        import wave

        import numpy as np

        with wave.open(str(wav), "rb") as w:
            pcm = w.readframes(w.getnframes())
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        wav.unlink(missing_ok=True)

    print(f"[asr] {model_size} / {device} / {compute} 转写中…", file=sys.stderr)
    try:
        seg_iter, info = model.transcribe(
            audio, language=lang, vad_filter=True, beam_size=5,
            word_timestamps=words,
        )
        segs = list(seg_iter)
    except RuntimeError as e:  # noqa: BLE001
        msg = str(e)
        if "cublas" in msg.lower() or "cudnn" in msg.lower():
            raise SystemExit(
                f"[asr] GPU 推理缺 CUDA 运行时：{msg[:200]}\n"
                f"      装 nvidia-cublas-cu12 与 nvidia-cudnn-cu12 后重试；"
                f"或改用 --device cpu --compute int8"
            ) from e
        raise

    items = []
    for s in segs:
        item = {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        if words and s.words:
            item["words"] = [{"start": round(w.start, 2), "end": round(w.end, 2),
                              "w": w.word} for w in s.words]
        items.append(item)

    data = {
        "model": model_size, "device": device, "compute_type": compute,
        "language": info.language, "duration_sec": round(info.duration, 2),
        "segments": items, "text": "".join(x["text"] for x in items),
        "created_at": now_iso(),
    }
    write_json(out_json, data)
    print(f"[asr] {len(items)} 句 / {data['duration_sec']}s", file=sys.stderr)
    return data


# ---------------------------------------------------------------- 镜头切点

def scene_cuts(video: Path, threshold: float = 0.30, max_cuts: int = 80) -> list[float]:
    """用 ffmpeg 场景检测取切点。解析 showinfo 的 pts_time。"""
    p = subprocess.run(
        [str(ffmpeg()), "-hide_banner", "-i", str(video), "-filter:v",
         f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
    )
    cuts = []
    for m in re.finditer(r"pts_time:\s*([0-9.]+)", p.stderr or ""):
        try:
            t = float(m.group(1))
        except ValueError:
            continue
        if not cuts or t - cuts[-1] > 0.20:
            cuts.append(round(t, 2))
    return cuts[:max_cuts]


def shot_table(cuts: list[float], duration: float) -> list[dict]:
    bounds = [0.0] + [c for c in cuts if 0.2 < c < duration - 0.1] + [duration]
    shots = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b - a < 0.15:
            continue
        shots.append({"idx": len(shots) + 1, "start": round(a, 2),
                      "end": round(b, 2), "dur": round(b - a, 2)})
    return shots


# ---------------------------------------------------------------- 抽帧

def pick_times(duration: float, shots: list[dict], n: int) -> list[float]:
    """每个镜头取中点（保证覆盖每个切点），不够再用均匀点补足。"""
    times = [round((s["start"] + s["end"]) / 2, 2) for s in shots]
    if len(times) < n:
        step = duration / (n + 1)
        times += [round(step * i, 2) for i in range(1, n + 1)]
    times = sorted({t for t in times if 0.05 < t < duration - 0.05})
    if len(times) <= n:
        return times
    # 超了就等距抽稀，保留首尾
    idx = [round(i * (len(times) - 1) / (n - 1)) for i in range(n)]
    return [times[i] for i in sorted(set(idx))]


def extract_frames(video: Path, out_dir: Path, times: list[float]) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for i, ts in enumerate(times, 1):
        out = out_dir / f"f{i:02d}_{ts:.1f}s.jpg"
        p = run([ffmpeg(), "-v", "error", "-i", video, "-ss", str(ts),
                 "-frames:v", "1", "-q:v", "3", "-y", out], timeout=180, check=False)
        if p.returncode == 0 and out.exists():
            made.append({"path": str(out), "ts": ts})
    return made


def contact_sheet(frames: list[dict], out_path: Path, cols: int = 4, cell_w: int = 360) -> str | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("[frame] 没装 Pillow，跳过联系表", file=sys.stderr)
        return None
    if not frames:
        return None
    imgs = []
    for f in frames:
        try:
            im = Image.open(f["path"]).convert("RGB")
        except OSError:
            continue
        h = round(cell_w * im.height / max(im.width, 1))
        imgs.append((im.resize((cell_w, h)), f["ts"]))
    if not imgs:
        return None
    cell_h = max(i.height for i, _ in imgs) + 26
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    d = ImageDraw.Draw(sheet)
    for i, (im, ts) in enumerate(imgs):
        x, y = (i % cols) * cell_w, (i // cols) * cell_h
        sheet.paste(im, (x, y))
        d.text((x + 6, y + im.height + 6), hhmmss(ts), fill="black")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=86)
    return str(out_path)


def cut_clips(video: Path, shots: list[dict], out_dir: Path, n: int) -> list[dict]:
    """切出 n 段连续片段，用于判断运镜/动效（静帧看不出运动）。"""
    if n <= 0 or not shots:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    picks = shots if len(shots) <= n else [shots[round(i * (len(shots) - 1) / (n - 1))] for i in range(n)]
    made = []
    for s in {x["idx"]: x for x in picks}.values():
        dur = min(max(s["dur"], 1.2), 4.0)
        out = out_dir / f"shot{s['idx']:02d}_{s['start']:.1f}s.mp4"
        p = run([ffmpeg(), "-v", "error", "-ss", str(s["start"]), "-i", video,
                 "-t", str(dur), "-an", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "26", "-y", out], timeout=300, check=False)
        if p.returncode == 0 and out.exists():
            made.append({"path": str(out), "start": s["start"], "dur": round(dur, 2)})
    return made


# ---------------------------------------------------------------- 证据输出

def evidence_md(ev: dict) -> str:
    m = ev["meta"]
    lines = [
        f"# 拆解证据包 · {m.get('title') or ev.get('slug')}",
        "",
        f"- 来源：{m.get('url') or m.get('source_page') or '本地文件'}",
        f"- 平台 / 作者：{m.get('platform')} / {m.get('author') or '未知'}",
        f"- 时长 / 画幅 / 帧率：{m.get('duration_sec')}s · {m.get('width')}x{m.get('height')} · {m.get('fps')}fps",
        f"- 镜头数（场景检测）：{len(ev['shots'])}　切点阈值 0.30",
        f"- 转写：{ev['transcript'].get('model')} / {ev['transcript'].get('device')}，{len(ev['transcript'].get('segments') or [])} 句",
        "",
        "## 一、镜头表（切点来自场景检测，时间为秒）",
        "",
        "| # | 入点 | 出点 | 时长 |",
        "|---|------|------|------|",
    ]
    for s in ev["shots"][:60]:
        lines.append(f"| {s['idx']} | {s['start']:.2f} | {s['end']:.2f} | {s['dur']:.2f} |")
    if len(ev["shots"]) > 60:
        lines.append(f"| … | 共 {len(ev['shots'])} 个镜头，其余见 evidence.json | | |")

    lines += ["", "## 二、逐句转写（口播原话）", ""]
    for s in ev["transcript"].get("segments") or []:
        lines.append(f"- `{hhmmss(s['start'])} → {hhmmss(s['end'])}` {s['text']}")

    lines += ["", "## 三、抽帧索引", ""]
    for f in ev["frames"]:
        lines.append(f"- `{hhmmss(f['ts'])}` {Path(f['path']).name}")
    if ev.get("contact_sheet"):
        lines.append(f"- 联系表：`{ev['contact_sheet']}`")
    if ev.get("clips"):
        lines += ["", "## 四、连续片段（判断运镜/动效用）", ""]
        for c in ev["clips"]:
            lines.append(f"- `{hhmmss(c['start'])}` 起 {c['dur']}s：{Path(c['path']).name}")

    lines += [
        "",
        "## 五、拆解要求（给编排层）",
        "",
        "按下面八项写 analysis.md，每条结论必须能指回上面的时间点；",
        "指不回去的写「推断」，不要写成事实。",
        "",
        "1. **钩子**：前 3 秒做了什么（画面 + 第一句话），为什么能留住人",
        "2. **结构**：把全片切成 3–6 个功能段（钩子/铺垫/论证/转折/落点），标时间区间",
        "3. **信息密度**：每 10 秒推进几个新信息点；哪一段是废话",
        "4. **视觉语法**：景别、机位、字幕位置与字号、配色、图形元素，各举一个时间点",
        "5. **声音**：语速（字/秒，可用转写字数除时长）、停顿、BGM 有无、音效点位",
        "6. **可复用装置**：这支片子独有的、能搬到别的主题上的手法（列 3 条以内）",
        "7. **不能学的**：具体文案、具体镜头、他人素材/音乐/logo",
        "8. **证据强度**：静帧和 1fps 抽帧判断不了运动曲线、转场类型、运镜速度；",
        "   这类结论必须标注「推断」，或先看 clips/ 里的连续片段再下结论。",
        "",
        f"_生成时间：{ev['created_at']}_",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成视频拆解证据包")
    ap.add_argument("--video", help="本地视频路径")
    ap.add_argument("--url", help="视频链接（会先调用 fetch.py 下载）")
    ap.add_argument("--out", required=True, help="工作目录")
    ap.add_argument("--frames", type=int, default=24, help="抽帧数量（默认 24）")
    ap.add_argument("--clips", type=int, default=6, help="切几段连续片段，0 关闭")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute", default="int8_float16")
    ap.add_argument("--words", action="store_true", help="词级时间戳（更慢）")
    ap.add_argument("--skip-transcribe", action="store_true")
    ap.add_argument("--scene-threshold", type=float, default=0.30)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    video = Path(a.video) if a.video else None
    meta_path = out / "meta.json"
    if video is None and a.url:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "fetch.py"), a.url, "--out", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            print(r.stdout or r.stderr, file=sys.stderr)
            raise SystemExit("[fetch] 下载失败")
        video = Path(json.loads(r.stdout)["path"])
    if video is None:
        for p in out.glob("source.*"):
            if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".flv"):
                video = p
                break
    if video is None or not video.exists():
        raise SystemExit("[analyze] 需要 --video 或 --url（或目录里已有 source.mp4）")

    info = probe(video)
    meta = read_json(meta_path) if meta_path.exists() else {}
    meta = {**info, **{k: v for k, v in meta.items() if v not in (None, "")}, "path": str(video)}
    write_json(meta_path, meta)

    duration = float(info.get("duration_sec") or 0)
    print(f"[analyze] {video.name} · {duration}s · {info.get('width')}x{info.get('height')}", file=sys.stderr)

    transcript = {"segments": [], "text": "", "model": None, "device": None}
    if not a.skip_transcribe:
        transcript = transcribe(video, out / "transcript.json", a.model, a.device,
                                a.compute, a.lang, a.words)

    cuts = scene_cuts(video, a.scene_threshold)
    shots = shot_table(cuts, duration)
    times = pick_times(duration, shots, a.frames)
    frames = extract_frames(video, out / "frames", times)
    sheet = contact_sheet(frames, out / "contact_sheet.jpg")
    clips = cut_clips(video, shots, out / "clips", a.clips)

    ev = {
        "slug": out.name,
        "created_at": now_iso(),
        "meta": meta,
        "shots": shots,
        "cuts": cuts,
        "transcript": transcript,
        "frames": frames,
        "contact_sheet": sheet,
        "clips": clips,
    }
    write_json(out / "evidence.json", ev)
    (out / "evidence.md").write_text(evidence_md(ev), encoding="utf-8")

    summary = {
        "ok": bool(frames) and bool(transcript.get("segments")),
        "out_dir": str(out),
        "video": str(video),
        "duration_sec": duration,
        "size": f"{info.get('width')}x{info.get('height')}",
        "shots": len(shots),
        "segments": len(transcript.get("segments") or []),
        "frames": len(frames),
        "clips": len(clips),
        "evidence_md": str(out / "evidence.md"),
        "contact_sheet": sheet,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
