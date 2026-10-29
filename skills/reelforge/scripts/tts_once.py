"""把一段文字合成成 mp3（给 wvp 的 step 级 TTS provider 用）。

    python tts_once.py --text "要念的话" --out /abs/path/1.mp3 [--persona ace]

走本地 IndexTTS 服务（没起会自动拉起），参考音频取 personas.yaml 的
voice.ref_audio，输出先用 wav，再用 ffmpeg 转 mp3。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import SKILL_DIR, ffmpeg  # noqa: E402
from personas import get as get_persona  # noqa: E402
from tts import ensure_server, tts_config  # noqa: E402


def synth_wav(base: str, text: str, ref_bytes: bytes) -> bytes:
    boundary = "----vf" + uuid.uuid4().hex
    body = bytearray()

    def field(name: str, value: str) -> None:
        body.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )

    field("text", text)
    field("interval_silence", "80")
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="spk_audio"; '
        f'filename="ref.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
    )
    body.extend(ref_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        base.rstrip("/") + "/api/v1/tts",
        data=bytes(body),
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "text/event-stream",
        },
    )
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
                raise SystemExit(f"[tts_once] 服务端报错: {ev.get('detail')}")
    if not wav_url:
        raise SystemExit("[tts_once] 服务端没有返回音频地址")
    with urllib.request.urlopen(base.rstrip("/") + urllib.parse.quote(wav_url, safe="/:?=&%"), timeout=120) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True, help="目标 mp3 绝对路径")
    ap.add_argument("--persona", default=None)
    ap.add_argument("--ref-audio", default=None)
    a = ap.parse_args()

    text = (a.text or "").strip()
    if not text:
        raise SystemExit("[tts_once] 空文本")

    persona = get_persona(a.persona)
    voice = persona.get("voice") or {}
    ref = Path(a.ref_audio or voice.get("ref_audio") or "")
    if not ref.exists():
        raise SystemExit(f"[tts_once] 参考音频不存在: {ref}")

    base = (tts_config().get("http") or {}).get("url") or "http://127.0.0.1:7860"
    ensure_server(base)
    wav = synth_wav(base, text, ref.read_bytes())

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav)
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            [ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(tmp_path),
             "-codec:a", "libmp3lame", "-qscale:a", "2", str(out)],
            check=True, stdin=subprocess.DEVNULL,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    print(f"[tts_once] {out} ({len(text)} 字)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
