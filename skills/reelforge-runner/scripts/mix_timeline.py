"""mix_timeline.py —— 把逐拍旁白贴回录屏，输出成片 + SRT/ASS 字幕（可选烧录）。

与具体章节数解耦：章节与拍数从 `audio-segments.json` 读，不再写死。

典型流程：
  node record_auto.mjs --url ... --out out/raw.webm
  python mix_timeline.py --raw out/raw.webm --timeline out/raw.timeline.json \
      --segments audio-segments.json --audio-dir public/audio --out out/final.mp4 --srt out/final.srt

可选：
  --fps 30            输出帧率（源 25fps 会补帧）
  --trail 0.2         每拍音频后的呼吸位（与 wvp 的 trailMs 对齐）
  --burn              把字幕烧进画面
  --font "Microsoft YaHei" / --font-size 46 / --margin-v 72
  --no-trim           不裁同步白块（默认裁）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000


def ff(args: list[str], **kw) -> bytes:
    return subprocess.run(["ffmpeg", "-v", "error", *args], check=True, stdout=subprocess.PIPE, **kw).stdout


def detect_marker(raw: Path, fps: int = 25, window: float = 15.0) -> tuple[float, float] | None:
    """返回 (白块第一帧, 白块最后一帧结束)；找不到返回 None。"""
    data = ff(["-t", str(window), "-i", str(raw), "-vf", f"fps={fps},scale=320:180,format=gray",
               "-f", "rawvideo", "-"])
    frame = 320 * 180
    hits = []
    for i in range(len(data) // frame):
        f = np.frombuffer(data[i * frame:(i + 1) * frame], dtype=np.uint8).reshape(180, 320)
        if f[150:180, 290:320].mean() > 185:
            hits.append(i)
    if not hits:
        return None
    return hits[0] / fps, (hits[-1] + 1) / fps


def chapter_order(segments: list[dict]) -> list[tuple[str, int]]:
    order: list[tuple[str, int]] = []
    for s in segments:
        cid = s["chapter"]
        if not order or order[-1][0] != cid:
            order.append([cid, 0])
        order[-1][1] = max(order[-1][1], int(s["step"]))
    return [(c, n) for c, n in order]


def collect_steps(timeline: dict, chapters: list[tuple[str, int]]) -> list[tuple[float, str, int]]:
    """把采样折叠成 (相对秒, chapter, step0)。"""
    t0 = timeline.get("tStart") or timeline.get("tSpace") or timeline.get("t_start") or 0
    prev = None
    out = []
    for s in timeline.get("samples", []):
        k = (s.get("ci", -1), s.get("step", -1))
        if k[0] < 0 or k[1] < 0 or k == prev:
            continue
        out.append(((s["t"] - t0) / 1000.0, chapters[k[0]][0], k[1]))
        prev = k
    return out


def srt_time(t: float) -> str:
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def ass_time(t: float) -> str:
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def write_ass(rows: list[tuple[float, float, str]], path: Path, font: str, size: int, margin_v: int) -> None:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H99000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [head]
    for a, b, text in rows:
        t = text.replace("\n", "\\N").replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{t}\n")
    path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--segments", required=True)
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--trail", type=float, default=0.2)
    ap.add_argument("--srt", default="")
    ap.add_argument("--burn", action="store_true")
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--font-size", type=int, default=44)
    ap.add_argument("--margin-v", type=int, default=72)
    ap.add_argument("--no-trim", action="store_true")
    a = ap.parse_args()

    raw = Path(a.raw)
    timeline = json.loads(Path(a.timeline).read_text(encoding="utf-8"))
    segments = json.loads(Path(a.segments).read_text(encoding="utf-8"))
    chapters = chapter_order(segments)
    steps = collect_steps(timeline, chapters)

    first, last = 0.0, 0.0
    if not a.no_trim and timeline.get("marker", True):
        mark = detect_marker(raw)
        if mark:
            first, last = mark
            print(f"[mix] marker {first:.2f}s → {last:.2f}s")
        else:
            print("[mix] 没找到同步白块，按 0 起点处理（确认 record_auto 画了 marker）", file=sys.stderr)
    shift = last - first

    # 没有采样（页面没有 .pb-*）→ 等距切分
    if not steps:
        n = len(segments)
        total = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(raw)
        ]).decode().strip()) - last
        steps = [(i * total / n, s["chapter"], int(s["step"]) - 1) for i, s in enumerate(segments)]
        print(f"[mix] 无 step 采样，按 {n} 段等距切分")

    vdur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(raw)
    ]).decode().strip())

    # audio-segments.json 的 step 是 1 基；时间轴里的 st 是 0 基，统一成 0 基
    text_by = {(s["chapter"], int(s["step"]) - 1): s["text"] for s in segments}
    audio_by = {(s["chapter"], int(s["step"]) - 1): s["audio"] for s in segments}

    bed = np.zeros((int((vdur - last) * SR) + SR * 5, 2), dtype=np.float32)
    rows: list[tuple[float, float, str]] = []
    last_end = 0.0
    for t, cid, st in steps:
        key = (cid, st)
        mp3 = Path(a.audio_dir) / audio_by.get(key, f"{cid}/{st + 1}.mp3")
        text = text_by.get(key, "").strip()
        if mp3.exists():
            pcm = ff(["-i", str(mp3), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"])
            wav = np.frombuffer(pcm, dtype=np.float32).reshape(-1, 2)
        else:
            wav = np.zeros((0, 2), dtype=np.float32)
        off = t - shift
        i0 = int(off * SR)
        if i0 < 0:
            wav = wav[-i0:]
            i0 = 0
        n = min(len(wav), len(bed) - i0)
        if n > 0:
            bed[i0:i0 + n] += wav[:n]
            last_end = max(last_end, off + n / SR)
        if text:
            rows.append((max(0.0, off), text))

    total = min(vdur - last, last_end + 0.9)
    bed = bed[: int(total * SR)]
    peak = float(np.max(np.abs(bed))) or 1.0
    bed = np.tanh(bed / max(peak, 0.8) * 0.9)
    bed = (bed * 32767).astype(np.int16)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bed_path = out.with_suffix(".bed.wav")
    with wave.open(str(bed_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bed.tobytes())

    for i in range(len(rows)):
        a0, _ = rows[i]
        b0 = rows[i + 1][0] - 0.05 if i + 1 < len(rows) else min(total, a0 + 4.0)
        rows[i] = (a0, max(a0 + 0.4, b0), rows[i][1])

    srt_path = Path(a.srt) if a.srt else out.with_suffix(".srt")
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    with srt_path.open("w", encoding="utf-8") as f:
        for i, (s0, s1, text) in enumerate(rows, 1):
            f.write(f"{i}\n{srt_time(s0)} --> {srt_time(s1)}\n{text}\n\n")
    ass_path = srt_path.with_suffix(".ass")
    write_ass(rows, ass_path, a.font, a.font_size, a.margin_v)

    vf = f"fps={a.fps},format=yuv420p"
    if a.burn:
        p = str(ass_path).replace("\\", "/").replace(":", "\\:")
        vf = f"fps={a.fps},ass='{p}',format=yuv420p"

    cmd = ["ffmpeg", "-v", "error", "-y",
           "-ss", f"{last:.3f}", "-i", str(raw), "-i", str(bed_path),
           "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a",
           "-c:v", "libx264", "-crf", "18", "-preset", "medium",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-t", f"{total:.2f}", str(out)]
    subprocess.run(cmd, check=True)
    print(f"[mix] {out}  ({total:.1f}s)")
    print(f"[mix] srt {srt_path}")
    print(f"[mix] ass {ass_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
