"""探测本机 EAC design world（剪辑插件）安装了哪些模板 / 动效，输出 JSON 风格包。

用法：
  python scripts/eac_probe.py            # 人类可读摘要
  python scripts/eac_probe.py --json     # 机器读（给 runner 决策用）
  python scripts/eac_probe.py --motion 转场 --json

设计原则：不依赖 MCP、不调用插件进程，只读插件安装目录里的 SKILL.md / catalog.json，
所以离线、无插件会话时也能用；读不到就返回 installed=false，调用方退回纯 wvp 流程。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def find_root() -> Path | None:
    env = os.environ.get("EAC_HOME")
    cands = [Path(env)] if env else []
    home = Path.home()
    cands += [home / "Apps" / "eac-design-world", home / "apps" / "eac-design-world"]
    users = Path("C:/Users")
    if users.is_dir():
        cands += sorted(users.glob("*/Apps/eac-design-world"))
    for c in cands:
        if (c / "vendor").is_dir():
            return c
    return None


def front_matter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
    return data


def scan_templates(root: Path) -> list[dict]:
    out = []
    for d in sorted((root / "vendor").iterdir()):
        skill = d / "SKILL.md"
        if not d.is_dir() or not skill.exists() or d.name == "video-shotcraft":
            continue
        meta = front_matter(skill.read_text(encoding="utf-8", errors="replace"))
        entry = d / "templates" / "film-template.html"
        out.append({
            "id": d.name,
            "name": meta.get("name", d.name),
            "description": meta.get("description", "")[:120],
            "path": str(d),
            "renderable": entry.exists(),
            "entry": str(entry) if entry.exists() else None,
        })
    return out


def scan_motions(root: Path) -> list[dict]:
    cat = root / "vendor" / "video-shotcraft" / "catalog.json"
    if not cat.exists():
        return []
    data = json.loads(cat.read_text(encoding="utf-8"))
    items = []
    for t in data.get("templates") or []:
        items.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "category": t.get("category"),
            "recipe": t.get("recipe"),
            "energy": t.get("energy"),
            "duration": t.get("duration"),
            "recommended": bool(t.get("recommended")),
            "renderable": t.get("renderable", False),
            "license": t.get("license"),
            "sourceFiles": t.get("sourceFiles") or [],
        })
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--motion", default="", help="按分类/名称过滤动效")
    a = ap.parse_args()

    root = find_root()
    if not root:
        payload = {"installed": False, "reason": "没找到 eac-design-world/vendor"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    templates = scan_templates(root)
    motions = scan_motions(root)
    if a.motion:
        key = a.motion.lower()
        motions = [m for m in motions if key in json.dumps(m, ensure_ascii=False).lower()]

    payload = {
        "installed": True,
        "eacRoot": str(root),
        "templates": templates,
        "motions": motions,
        "counts": {"templates": len(templates), "motions": len(motions)},
        "licenseNote": "video-shotcraft 为 Apache-2.0（成片需署名）；motion-promo-film 模板按其 NOTICE 使用；PolyForm NC 动效库商用需授权。",
    }
    if a.json or a.motion:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"EAC: {root}")
    print("模板：")
    for t in templates:
        print(f"  - {t['id']:<24} renderable={str(t['renderable']):<5} {t['name'][:40]}")
    print(f"动效：{len(motions)} 条（前 12）")
    for m in motions[:12]:
        print(f"  - {m['id']:<38} {str(m['category'])[:8]:<8} {str(m['energy'])[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
