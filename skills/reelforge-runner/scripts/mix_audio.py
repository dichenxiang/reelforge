"""把 wvp 的 step 音频按顺序拼成一条旁白轨，给 record.mjs 的 --audio 用。

    python mix_audio.py --presentation work/demo/presentation --gap 0.35 --out out/narration.mp3

注意：这是「按顺序拼接」，不是按页面实际播放时间对齐。只用于无人值守时
先出一条可听的成片；要严格同步请人工 OBS 录屏。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--presentation", required=True)
    ap.add_argument("--gap", type=float, default=0.35)
    ap.add_argument("--out", default="out/narration.mp3")
    a = ap.parse_args()

    proj = Path(a.presentation)
    seg_file = proj / "audio-segments.json"
    if not seg_file.exists():
        raise SystemExit("[mix] 先跑 npm run extract-narrations")
    segs = json.loads(seg_file.read_text(encoding="utf-8"))

    files = []
    for s in segs:
        p = proj / "public" / "audio" / s["audio"]
        if not p.exists():
            raise SystemExit(f"[mix] 缺少音频：{p}，先跑 synthesize-audio")
        files.append(p)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in files:
            f.write(f"file '{p.as_posix()}'\n")
            if a.gap > 0:
                f.write(f"file '{(Path(__file__).parent / '_silence.mp3').as_posix()}'\n")
        list_path = Path(f.name)

    silence = Path(__file__).parent / f"_silence.mp3"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"anullsrc=r=44100:cl=mono", "-t", str(a.gap),
                    "-q:a", "9", str(silence)], check=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat",
                    "-safe", "0", "-i", str(list_path), "-c:a", "libmp3lame",
                    "-q:a", "2", str(out)], check=True)
    list_path.unlink(missing_ok=True)
    silence.unlink(missing_ok=True)
    print(f"[mix] {out}（{len(files)} 段，间隔 {a.gap}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
