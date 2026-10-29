"""读取账号人设。默认读 config/personas.yaml，存在 personas.local.yaml 时优先用它。

    python personas.py --list
    python personas.py --show ace
    python personas.py --prompt ace     # 打印可直接拼进写稿 prompt 的人设段落
    python personas.py --voice ace      # 打印音色配置（tts.py 用）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR  # noqa: E402

CONFIG_DIR = SKILL_DIR / "config"


def config_path() -> Path:
    local = CONFIG_DIR / "personas.local.yaml"
    return local if local.exists() else CONFIG_DIR / "personas.yaml"


def load() -> dict:
    try:
        import yaml
    except ImportError:
        raise SystemExit("[persona] 需要 PyYAML：python -m pip install pyyaml") from None
    path = config_path()
    if not path.exists():
        raise SystemExit(f"[persona] 找不到配置: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["_path"] = str(path)
    return data


def get(persona_id: str | None = None) -> dict:
    data = load()
    pid = persona_id or data.get("default_persona")
    personas = data.get("personas") or {}
    if pid not in personas:
        raise SystemExit(f"[persona] 没有 {pid}，可选：{', '.join(personas)}")
    p = dict(personas[pid])
    p["id"] = pid
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="账号人设读取")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show")
    ap.add_argument("--prompt")
    ap.add_argument("--voice")
    a = ap.parse_args()

    if a.list or (not a.show and not a.prompt and not a.voice):
        data = load()
        print(f"配置文件：{data['_path']}")
        for pid, p in (data.get("personas") or {}).items():
            mark = "*" if pid == data.get("default_persona") else " "
            v = (p.get("voice") or {})
            print(f" {mark} {pid:<12} {p.get('display_name', ''):<8} {p.get('account_type', ''):<10} "
                  f"{v.get('voice', '')} {v.get('rate', '')}")
        return 0

    if a.show:
        print(json.dumps(get(a.show), ensure_ascii=False, indent=2))
        return 0
    if a.voice:
        print(json.dumps(get(a.voice).get("voice") or {}, ensure_ascii=False))
        return 0
    if a.prompt:
        p = get(a.prompt)
        print(p.get("prompt_block", "").strip())
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
