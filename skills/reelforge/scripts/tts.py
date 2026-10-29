"""按人设把 script.json 的每一拍合成为语音，拼成整条旁白并给出真实时间轴。

    python tts.py --work work/xxx --persona ace
    python tts.py --work work/xxx --persona gatekeeper --gap 0.18
    python tts.py --work work/xxx --provider cmd \
        --cmd-template '"{python}" infer.py --text "{text}" --out "{out}" --voice "{voice}"'

默认 provider = edge（微软 Edge 在线音色，免费、无需 key、音色稳定）。
需要本地克隆音色时用 provider = cmd 接 IndexTTS 之类（见 references/tts.md）。

产出（默认 <work>/showreel/audio/）：
    beat_01.wav …   每拍一条，48kHz 单声道
    narration.wav   整条旁白（含拍间停顿）
    narration.json  真实时间轴，喂给 timeline.js
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, ffmpeg, probe, read_json, run, write_json  # noqa: E402
from personas import get as get_persona  # noqa: E402

WAV = ["-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le"]


def tts_config() -> dict:
    path = SKILL_DIR / "config" / "tts.yaml"
    if not path.exists():
        return {}
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _server_alive(base: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_server(base: str) -> None:
    """服务没起就按 config/tts.yaml 的 start_cmd 自动拉起（常驻，不随本次结束）。"""
    if _server_alive(base):
        return
    cfg = tts_config().get("http") or {}
    if not cfg.get("autostart", True):
        raise SystemExit(
            f"[tts] IndexTTS 服务未启动：{base}\n"
            f"      先跑 start_server.bat，或在 config/tts.yaml 打开 autostart"
        )
    cwd = Path(os.path.expandvars(str(cfg.get("start_cwd", ""))))
    cmd = [str(c) for c in (cfg.get("start_cmd") or ["runtime/python.exe", "server.py", "--port", "7860"])]
    exe = cwd / cmd[0]
    if not exe.exists():
        raise SystemExit(f"[tts] 找不到服务端 {exe}，检查 config/tts.yaml 的 start_cwd")
    print(f"[tts] 服务未运行，正在启动 {exe.name} …", file=sys.stderr)
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    log_path = Path(os.environ.get("TEMP", ".")) / "vf-tts-server.log"
    log = open(log_path, "ab", buffering=0)
    log.write(f"\n==== start {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n".encode())
    subprocess.Popen(
        [str(exe), *cmd[1:]], cwd=str(cwd),
        stdout=log, stderr=log, stdin=subprocess.DEVNULL,
        creationflags=flags, close_fds=True,
    )
    log.close()
    timeout = int(cfg.get("startup_timeout", 90))
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _server_alive(base):
            print(f"[tts] 服务已就绪（{round(time.time() - t0, 1)}s）", file=sys.stderr)
            return
        time.sleep(1)
    raise SystemExit(f"[tts] 服务启动超时（{timeout}s），手动跑 start_server.bat 看日志")


def http_batch(beats: list[dict], out_dir: Path, voice: dict, base_url: str,
               ref_audio: str | None) -> list[Path]:
    """调本地 IndexTTS 服务的 /api/v1/tts（表单上传 + SSE 进度），返回原始 wav。"""
    import urllib.parse
    import urllib.request
    import uuid

    ref = Path(ref_audio or voice.get("ref_audio") or "")
    if not ref.exists():
        raise SystemExit(
            f"[tts] 缺少参考音频: {ref}\n"
            f"      在 config/personas.yaml 的 voice.ref_audio 里指定 10–20 秒干净人声"
        )
    base = base_url.rstrip("/")
    api = base + "/api/v1/tts"
    raw_dir = out_dir / "_http_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    audio = ref.read_bytes()
    outs: list[Path] = []

    for i, b in enumerate(beats, 1):
        text = b["text"].strip()
        boundary = "----vf" + uuid.uuid4().hex
        body = bytearray()

        def field(name: str, value: str) -> None:
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; '
                        f'name="{name}"\r\n\r\n{value}\r\n'.encode())

        field("text", text)
        field("interval_silence", "120")
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="spk_audio"; '
                    f'filename="ref.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
        body.extend(audio)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(api, data=bytes(body), method="POST", headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "text/event-stream",
        })
        print(f"[tts] {b.get('id') or f'b{i}'} · {len(text)} 字（IndexTTS 服务）", file=sys.stderr)
        wav_url = None
        with urllib.request.urlopen(req, timeout=900) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if ev.get("type") == "done":
                    wav_url = ev.get("wav")
                elif ev.get("type") == "error":
                    raise SystemExit(f"[tts] 服务端报错: {ev.get('detail')}")
        if not wav_url:
            raise SystemExit("[tts] 服务端没有返回音频地址")
        out = raw_dir / f"beat_{i:02d}.wav"
        safe_url = base + urllib.parse.quote(wav_url, safe="/:?=&%")
        with urllib.request.urlopen(safe_url, timeout=120) as r:
            out.write_bytes(r.read())
        outs.append(out)
    return outs


def edge_one(text: str, out_mp3: Path, voice: dict) -> None:
    try:
        import edge_tts
    except ImportError:
        raise SystemExit("[tts] 需要 edge-tts：python -m pip install edge-tts") from None

    comm = edge_tts.Communicate(
        text,
        voice.get("voice") or "zh-CN-YunxiNeural",
        rate=voice.get("rate") or "+0%",
        pitch=voice.get("pitch") or "+0Hz",
        volume=voice.get("volume") or "+0%",
    )
    asyncio.run(comm.save(str(out_mp3)))


def cmd_one(text: str, out_wav: Path, voice: dict, template: str) -> None:
    cmd = template.format(
        python=sys.executable, text=text, out=str(out_wav),
        voice=voice.get("voice", ""), rate=voice.get("rate", ""),
    )
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"合成命令失败：{(p.stderr or p.stdout or '')[:400]}")


def to_wav(src: Path, dst: Path) -> None:
    run([ffmpeg(), "-v", "error", "-i", src, "-vn", *WAV, "-y", dst])


def silence(dst: Path, seconds: float) -> None:
    run([ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
         f"anullsrc=r=48000:cl=mono", "-t", f"{seconds:.3f}", *WAV, "-y", dst])


def main() -> int:
    ap = argparse.ArgumentParser(description="按人设合成旁白")
    ap.add_argument("--work", required=True)
    ap.add_argument("--persona", default=None, help="ace / gatekeeper，默认取 personas.yaml 的 default")
    ap.add_argument("--out", default=None, help="默认 <work>/showreel/audio")
    ap.add_argument("--provider", default=None, choices=["edge", "http", "cmd"],
                    help="默认取人设 voice.provider，缺省 edge")
    ap.add_argument("--ref-audio", default=None, help="IndexTTS 参考音频（10–20 秒干净人声）")
    ap.add_argument("--server", default=None,
                    help="IndexTTS 服务地址，默认取 config/tts.yaml 的 http.url")
    ap.add_argument("--cmd-template", default=None)
    ap.add_argument("--gap", type=float, default=0.12, help="拍间停顿秒数")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    work = Path(a.work)
    script_path = work / "script.json"
    if not script_path.exists():
        raise SystemExit(f"[tts] 找不到 {script_path}（先跑阶段 2 写稿）")
    script = read_json(script_path)
    beats = script.get("beats") or []
    if not beats:
        raise SystemExit("[tts] script.json 没有 beats")

    persona = get_persona(a.persona)
    voice = persona.get("voice") or {}
    provider = a.provider or voice.get("provider") or "edge"
    out_dir = Path(a.out) if a.out else work / "showreel" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    if provider == "cmd" and not a.cmd_template:
        raise SystemExit("[tts] provider=cmd 需要 --cmd-template（见 references/tts.md）")

    parts: list[tuple[str, Path]] = []
    valid = [b for b in beats if (b.get("text") or "").strip()]

    if provider == "http":
        base = a.server or (tts_config().get("http") or {}).get("url") or "http://127.0.0.1:7860"
        ensure_server(base)
        raws = http_batch(valid, out_dir, voice, base, a.ref_audio)
        for i, (b, raw) in enumerate(zip(valid, raws), 1):
            tag = b.get("id") or f"b{i}"
            wav = out_dir / f"beat_{i:02d}.wav"
            if wav.exists() and not a.force:
                parts.append((tag, wav))
                raw.unlink(missing_ok=True)
                continue
            print(f"[tts] {tag} · {persona['display_name']} · {len(b['text'])} 字（IndexTTS）",
                  file=sys.stderr)
            to_wav(raw, wav)
            raw.unlink(missing_ok=True)
            parts.append((tag, wav))
        for d in ("_http_raw",):
            rd = out_dir / d
            if rd.exists() and not any(rd.iterdir()):
                rd.rmdir()
    else:
        for i, b in enumerate(valid, 1):
            text = b["text"].strip()
            tag = b.get("id") or f"b{i}"
            wav = out_dir / f"beat_{i:02d}.wav"
            if wav.exists() and not a.force:
                parts.append((tag, wav))
                continue
            print(f"[tts] {tag} · {persona['display_name']} · {len(text)} 字", file=sys.stderr)
            if provider == "edge":
                mp3 = out_dir / f"beat_{i:02d}.mp3"
                edge_one(text, mp3, voice)
                to_wav(mp3, wav)
                mp3.unlink(missing_ok=True)
            else:
                cmd_one(text, wav, voice, a.cmd_template)
            parts.append((tag, wav))

    if not parts:
        raise SystemExit("[tts] 没有可合成的文本")

    gap_wav = out_dir / "_gap.wav"
    if a.gap > 0:
        silence(gap_wav, a.gap)

    # 用同格式 WAV 走 concat demuxer，避免二次编码走样
    list_path = out_dir / "_concat.txt"
    seq: list[Path] = []
    for i, (_, wav) in enumerate(parts):
        seq.append(wav)
        if a.gap > 0 and i < len(parts) - 1:
            seq.append(gap_wav)
    list_path.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in seq), encoding="utf-8"
    )
    narration = out_dir / "narration.wav"
    run([ffmpeg(), "-v", "error", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c", "copy", "-y", narration])

    # 真实时间轴
    t = 0.0
    tl = []
    for tag, wav in parts:
        d = float(probe(wav).get("duration_sec") or 0)
        tl.append({"id": tag, "start": round(t, 3), "end": round(t + d, 3), "dur": round(d, 3)})
        t += d + (a.gap if a.gap > 0 else 0)
    total = float(probe(narration).get("duration_sec") or t)
    target = float(script.get("duration_sec") or 0)
    warn = []
    if target and abs(total - target) / target > 0.15:
        warn.append(f"旁白实际 {total:.2f}s，脚本目标 {target}s，偏差超过 15%：要么改稿，要么改片长，必须让用户确认")

    data = {
        "persona": persona["id"],
        "display_name": persona.get("display_name"),
        "provider": provider,
        "voice": voice,
        "gap": a.gap,
        "total_sec": round(total, 3),
        "beats": tl,
    }
    write_json(out_dir / "narration.json", data)
    for p in (list_path, gap_wav):
        p.unlink(missing_ok=True)

    print(json.dumps({
        "ok": True, "wav": str(narration), "seconds": round(total, 2),
        "beats": len(tl), "warnings": warn, "timeline": str(out_dir / "narration.json"),
    }, ensure_ascii=False))
    return 0 if not warn else 2


if __name__ == "__main__":
    raise SystemExit(main())
