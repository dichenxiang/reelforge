"""film_from_beats.py —— 从 script.json + 旁白时间轴生成路线 B 的确定性 film.html 骨架。

    python film_from_beats.py --work work/demo --out work/demo/film/film.html --title "片名"

输入（按优先级）：
  1) <work>/narration.json      （tts.py 产物，含每拍 start/dur）
  2) <work>/audio-segments.json + --audio-dir （逐拍 mp3，ffprobe 取时长）
输出：
  film.html                     满足 window.__FPS/__DUR/__seek/__ready 契约
  （可选 --style 把外部 CSS 一起内联；默认内联 assets/eac/style-pack.css 的颗粒/暗角）

注意：这是**骨架**（每拍一屏字幕卡）。要模板级浮窗 UI，按 motion-promo-film 的
STYLE.md 把 section 换成真实 DOM，时间轴不用改。
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
STYLE_PACK = SKILL / "assets" / "eac" / "style-pack.css"


def probe_dur(path: Path) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)
        ], stderr=subprocess.DEVNULL)
        return float(out.decode().strip())
    except Exception:
        return 0.0


def beats_with_times(work: Path, audio_dir: Path | None) -> list[dict]:
    nar = work / "narration.json"
    if nar.exists():
        data = json.loads(nar.read_text(encoding="utf-8"))
        beats = data.get("beats") or []
        return [{"text": b.get("text", ""), "start": float(b["start"]), "dur": float(b.get("dur") or 3)} for b in beats]
    seg = work / "audio-segments.json"
    if not seg.exists():
        seg = work / "presentation" / "audio-segments.json"
    if not seg.exists():
        raise SystemExit("[film] 需要 narration.json 或 audio-segments.json（work 或 presentation/ 下）")
    items = json.loads(seg.read_text(encoding="utf-8"))
    out, t = [], 0.0
    for s in items:
        p = (audio_dir or work / "presentation" / "public" / "audio") / s["audio"]
        d = probe_dur(p) or 2.8
        out.append({"text": s.get("text", ""), "start": t, "dur": d})
        t += d + 0.2
    return out


def build_html(title: str, beats: list[dict], accent: str, bg: str, style: str) -> str:
    data = json.dumps(beats, ensure_ascii=False)
    total = beats[-1]["start"] + beats[-1]["dur"] + 0.9 if beats else 1.0
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:{bg}; --fg:#f2f4e6; --accent:{accent}; --mute:#879184; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; background:var(--bg); color:var(--fg);
  font-family:"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif; overflow:hidden; }}
#stage {{ position:fixed; inset:0; display:grid; place-items:center; padding:80px 100px; }}
.beat {{ position:absolute; inset:80px 100px; display:grid; align-content:center; gap:26px;
  opacity:0; transform:translateY(26px); will-change:opacity,transform; }}
.kicker {{ font:600 18px/1 ui-monospace,monospace; letter-spacing:.22em; color:var(--accent); }}
.line {{ font-size:64px; line-height:1.22; font-weight:700; letter-spacing:-0.01em; max-width:1500px; }}
.meta {{ position:fixed; left:100px; bottom:64px; font:500 15px ui-monospace,monospace;
  letter-spacing:.18em; color:var(--mute); }}
.bar {{ position:fixed; left:0; bottom:0; height:4px; width:0; background:var(--accent); }}
.eac-grain {{ position:fixed; inset:0; z-index:80; pointer-events:none; opacity:.045;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='180' height='180' filter='url(%23n)' opacity='0.55'/></svg>");
  background-size:180px 180px; }}
.eac-vignette {{ position:fixed; inset:0; z-index:79; pointer-events:none;
  background:radial-gradient(ellipse at 50% 45%, transparent 52%, rgba(0,0,0,.28) 100%); }}
{style}
</style>
</head>
<body>
<div id="stage"></div>
<div class="meta" id="meta"></div>
<div class="bar" id="bar"></div>
<div class="eac-grain"></div><div class="eac-vignette"></div>
<script>
const BEATS = {data};
const DUR = {total:.3f};
const FPS = 30;
const stage = document.getElementById('stage'), bar = document.getElementById('bar'), meta = document.getElementById('meta');
BEATS.forEach((b, i) => {{
  const el = document.createElement('div');
  el.className = 'beat';
  el.innerHTML = `<div class="kicker">— ${{String(i+1).padStart(2,'0')}} / ${{String(BEATS.length).padStart(2,'0')}}</div>
                  <div class="line">${{b.text.replace(/</g,'&lt;')}}</div>`;
  stage.appendChild(el);
  b.el = el;
}});
window.__FPS = FPS; window.__DUR = DUR;
window.__seek = (t) => {{
  t = Math.max(0, Math.min(DUR, t));
  let idx = 0;
  for (let i = 0; i < BEATS.length; i++) if (t >= BEATS[i].start) idx = i;
  const b = BEATS[idx], p = Math.min(1, Math.max(0, (t - b.start) / 0.45));
  const out = Math.min(1, Math.max(0, (b.start + b.dur - t) / 0.25));
  BEATS.forEach((x, i) => {{
    if (i !== idx) {{ x.el.style.opacity = 0; x.el.style.transform = 'translateY(26px)'; return; }}
    const e = 1 - Math.pow(1 - p, 3);
    const instant = (idx === 0 && t < 0.2) ? 1 : Math.min(e, out);
    x.el.style.opacity = String(instant);
    x.el.style.transform = `translateY(${{(1-e)*26}}px)`;
  }});
  bar.style.width = (t / DUR * 100).toFixed(2) + '%';
  meta.textContent = `MUSE / ${{String(idx+1).padStart(2,'0')}} · ${{(t).toFixed(1)}}s`;
}};
document.fonts.ready.then(() => {{
  const t0 = parseFloat(new URLSearchParams(location.search).get('t') || '0');
  window.__seek(t0); window.__ready = true;
}});
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--audio-dir", default="")
    ap.add_argument("--accent", default="#dfff43")
    ap.add_argument("--bg", default="#070b09")
    a = ap.parse_args()

    work = Path(a.work)
    title = a.title or json.loads((work / "script.json").read_text(encoding="utf-8")).get("title", work.name) \
        if (work / "script.json").exists() else (a.title or work.name)
    beats = beats_with_times(work, Path(a.audio_dir) if a.audio_dir else None)
    if not beats:
        raise SystemExit("[film] 没有节拍")

    style = STYLE_PACK.read_text(encoding="utf-8") if STYLE_PACK.exists() else ""
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(title, beats, a.accent, a.bg, style), encoding="utf-8")
    total = beats[-1]["start"] + beats[-1]["dur"] + 0.9
    print(json.dumps({"ok": True, "film": str(out), "beats": len(beats), "duration": round(total, 2)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
