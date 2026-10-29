"""ReelForge 冒烟测试：不依赖 GPU / 浏览器 / 网络，CI 里跑。

    python -m pytest -q tests

覆盖：状态机、任务包、混音时间轴纯函数、路线 B film 生成、preflight JSON。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "reelforge" / "scripts"
RUNNER = ROOT / "skills" / "reelforge-runner" / "scripts"


def run_py(script: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=check,
    )


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_state_flow(tmp_path: Path):
    work = tmp_path / "w"
    run_py(SCRIPTS / "state.py", "init", "--work", str(work), "--title", "t")
    run_py(SCRIPTS / "state.py", "set", "--work", str(work),
           "--meta", "render=B", "--meta", "template=demo")
    st = json.loads((work / "state.json").read_text(encoding="utf-8"))
    assert st["options"]["render"] == "B"
    assert st["options"]["template"] == "demo"

    run_py(SCRIPTS / "state.py", "gate", "--work", str(work), "--name", "script_gate")
    st = json.loads((work / "state.json").read_text(encoding="utf-8"))
    assert st["status"] == "awaiting_user" and st["gate"] == "script_gate"

    run_py(SCRIPTS / "state.py", "approve", "--work", str(work),
           "--gate", "script_gate", "--note", "ok")
    st = json.loads((work / "state.json").read_text(encoding="utf-8"))
    assert st["status"] == "approved"


def test_pack_writer_asks_and_no_default_persona(tmp_path: Path):
    work = tmp_path / "w"
    run_py(SCRIPTS / "state.py", "init", "--work", str(work), "--title", "t")
    run_py(SCRIPTS / "pack_task.py", "writer", "--work", str(work))
    text = (work / "tasks" / "writer.md").read_text(encoding="utf-8")
    assert "开工前先问清楚" in text
    assert "未指定人设" in text
    assert "素材决策" in text


def test_pack_runner_options(tmp_path: Path):
    work = tmp_path / "w"
    run_py(SCRIPTS / "state.py", "init", "--work", str(work), "--title", "t")
    run_py(SCRIPTS / "pack_task.py", "runner", "--work", str(work),
           "--render", "B", "--template", "motion-promo-film",
           "--tts-provider", "indextts", "--tts-preset", "demo", "--subs", "burn")
    text = (work / "tasks" / "runner.md").read_text(encoding="utf-8")
    assert "出片路线：B" in text
    assert "preset=demo" in text
    assert "字幕：burn" in text


def test_mix_timeline_helpers():
    m = load_module(RUNNER / "mix_timeline.py", "mix_timeline")
    assert m.srt_time(65.5) == "00:01:05,500"
    assert m.ass_time(65.5).startswith("0:01:05")
    segs = [
        {"chapter": "a", "step": 1, "text": "一", "audio": "a/1.mp3"},
        {"chapter": "a", "step": 2, "text": "二", "audio": "a/2.mp3"},
        {"chapter": "b", "step": 1, "text": "三", "audio": "b/1.mp3"},
    ]
    assert m.chapter_order(segs) == [("a", 2), ("b", 1)]
    timeline = {"tStart": 1000, "samples": [
        {"t": 1000, "ci": 0, "step": 0},
        {"t": 3000, "ci": 0, "step": 1},
        {"t": 5000, "ci": 1, "step": 0},
    ]}
    steps = m.collect_steps(timeline, m.chapter_order(segs))
    assert steps[0][1:] == ("a", 0)
    assert steps[-1][2] == 0


def test_film_from_beats(tmp_path: Path):
    f = load_module(RUNNER / "film_from_beats.py", "film_from_beats")
    html = f.build_html("片名", [
        {"text": "第一拍", "start": 0.0, "dur": 2.0},
        {"text": "第二拍", "start": 2.2, "dur": 2.0},
    ], "#dfff43", "#070b09", "")
    assert "window.__seek" in html
    assert "window.__DUR" in html
    assert "第一拍" in html
    assert "2.2" in html


def test_preflight_json():
    p = subprocess.run(
        [sys.executable, str(RUNNER / "preflight.py"), "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    data = json.loads(p.stdout)
    assert "checks" in data and isinstance(data["checks"], list)
    assert any(c["name"] == "python" for c in data["checks"])
    assert p.returncode in (0, 1)
