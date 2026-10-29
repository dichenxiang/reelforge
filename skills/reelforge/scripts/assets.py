"""reelforge 素材库：跨视频复用的图片 / 视频 / 音频 / 字体 / BGM。

库根目录默认 ~/.reelforge/library，可用 REELFORGE_LIBRARY 覆盖。
所有条目记录来源、授权、哈希、标签、用过它的片子；同一个文件只存一份。

    python assets.py init
    python assets.py add logo.png --tags brand,logo --source user --license own
    python assets.py search --tag gpu --type image
    python assets.py materialize --work work/demo --ids img_ab12cd,img_ef34gh
    python assets.py stats
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KIND_BY_EXT = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
    ".gif": "image", ".svg": "image", ".avif": "image",
    ".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio",
    ".flac": "audio", ".ogg": "audio",
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font",
    ".json": "data", ".csv": "data",
}


def library_root() -> Path:
    env = os.environ.get("REELFORGE_LIBRARY")
    return Path(env).expanduser() if env else Path.home() / ".reelforge" / "library"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_index(root: Path) -> dict:
    idx = root / "index.json"
    if not idx.exists():
        raise SystemExit(f"[assets] 素材库未初始化：{root}\n        先跑 python assets.py init")
    return json.loads(idx.read_text(encoding="utf-8"))


def write_index(root: Path, data: dict) -> None:
    data["updated_at"] = now()
    (root / "index.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_media(path: Path) -> dict:
    """尽量拿到尺寸/时长；拿不到不影响入库。"""
    info: dict = {"bytes": path.stat().st_size}
    kind = KIND_BY_EXT.get(path.suffix.lower(), "file")
    info["kind"] = kind
    if kind == "image":
        try:
            from PIL import Image
            with Image.open(path) as im:
                info["width"], info["height"] = im.size
        except Exception:
            pass
    if kind in ("video", "audio"):
        ff = shutil.which("ffprobe")
        if ff:
            try:
                out = subprocess.run(
                    [ff, "-v", "error", "-show_entries",
                     "format=duration:stream=width,height", "-of", "json", str(path)],
                    capture_output=True, text=True, timeout=30,
                ).stdout
                meta = json.loads(out or "{}")
                dur = (meta.get("format") or {}).get("duration")
                if dur:
                    info["duration_sec"] = round(float(dur), 3)
                for s in meta.get("streams") or []:
                    if s.get("width") and s.get("height"):
                        info["width"], info["height"] = s["width"], s["height"]
                        break
            except Exception:
                pass
    return info


def new_id(kind: str, digest: str) -> str:
    prefix = {"image": "img", "video": "vid", "audio": "aud",
              "font": "fnt", "data": "dat"}.get(kind, "ast")
    return f"{prefix}_{digest[:8]}"


def cmd_init(a) -> int:
    root = library_root()
    (root / "files").mkdir(parents=True, exist_ok=True)
    idx = root / "index.json"
    if not idx.exists():
        write_index(root, {"version": 1, "items": []})
    print(f"[assets] 库已就绪：{root}")
    return 0


def cmd_add(a) -> int:
    root = library_root()
    data = read_index(root)
    src = Path(a.path).expanduser()
    if not src.exists():
        raise SystemExit(f"[assets] 文件不存在：{src}")
    digest = sha256(src)
    for it in data["items"]:
        if it["sha256"] == digest:
            if a.tag:
                it["tags"] = sorted(set(it.get("tags", [])) | set(a.tag.split(",")))
                write_index(root, data)
            print(f"[assets] 已存在：{it['id']}（{it['path']}）")
            return 0
    kind = a.type or KIND_BY_EXT.get(src.suffix.lower(), "file")
    info = probe_media(src)
    kind = a.type or info.get("kind") or "file"
    item_id = new_id(kind, digest)
    rel = Path("files") / kind / f"{item_id}{src.suffix.lower()}"
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    item = {
        "id": item_id,
        "kind": kind,
        "path": rel.as_posix(),
        "original_name": src.name,
        "sha256": digest,
        "bytes": info.get("bytes"),
        "width": info.get("width"),
        "height": info.get("height"),
        "duration_sec": info.get("duration_sec"),
        "source": a.source,
        "origin": a.origin or "",
        "license": a.license,
        "tags": sorted({t.strip() for t in (a.tags or "").split(",") if t.strip()}),
        "note": a.note or "",
        "created_at": now(),
        "used_in": [],
    }
    data["items"].append(item)
    write_index(root, data)
    print(json.dumps({"ok": True, "id": item_id, "path": str(dest)}, ensure_ascii=False))
    return 0


def _match(it: dict, a) -> bool:
    kind = getattr(a, "type", None)
    tag = getattr(a, "tag", "")
    if kind and it.get("kind") != kind:
        return False
    if tag and not set(tag.split(",")).issubset(set(it.get("tags", []))):
        return False
    q = (getattr(a, "query", "") or "").lower()
    if q:
        hay = " ".join([
            it.get("id", ""), it.get("original_name", ""), it.get("note", ""),
            " ".join(it.get("tags", [])),
        ]).lower()
        if q not in hay:
            return False
    return True


def cmd_search(a) -> int:
    data = read_index(library_root())
    hits = [it for it in data["items"] if _match(it, a)]
    hits.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    hits = hits[: a.limit]
    if a.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print("[assets] 没有匹配的素材")
        return 0
    for it in hits:
        meta = "·".join(filter(None, [
            it.get("kind"),
            f"{it.get('width')}x{it.get('height')}" if it.get("width") else "",
            f"{it.get('duration_sec')}s" if it.get("duration_sec") else "",
            it.get("license"),
        ]))
        print(f"{it['id']:<14} {meta:<28} {'/'.join(it.get('tags', [])):<24} {it.get('original_name')}")
    return 0


def cmd_materialize(a) -> int:
    """把选中的素材复制进某个项目，并写 work/<slug>/assets.json 清单。"""
    root = library_root()
    data = read_index(root)
    by_id = {it["id"]: it for it in data["items"]}
    picks: list[dict] = []
    for raw in (a.ids or "").split(","):
        pid = raw.strip()
        if not pid:
            continue
        if pid not in by_id:
            raise SystemExit(f"[assets] 没有这个 id：{pid}")
        picks.append(by_id[pid])
    if not picks and (a.query or a.tag):
        picks = [it for it in data["items"] if _match(it, a)]

    work = Path(a.work)
    dest_dir = Path(a.to) if a.to else work / "presentation" / "public" / "assets"
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work / "assets.json"
    manifest = {"slug": work.name, "updated_at": now(), "items": []}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    known = {x["id"] for x in manifest.get("items", [])}
    copied = []
    for it in picks:
        src = root / it["path"]
        if not src.exists():
            print(f"[assets] 警告：{it['id']} 文件丢失，跳过", file=sys.stderr)
            continue
        dst = dest_dir / f"{it['id']}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        copied.append(str(dst))
        if it["id"] not in known:
            manifest["items"].append({
                "id": it["id"], "kind": it["kind"], "file": str(dst),
                "license": it.get("license"), "origin": it.get("origin"),
                "tags": it.get("tags", []),
            })
            known.add(it["id"])
        if work.name not in it.setdefault("used_in", []):
            it["used_in"].append(work.name)
    manifest["updated_at"] = now()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_index(root, data)
    print(json.dumps({"ok": True, "copied": copied, "manifest": str(manifest_path)},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_stats(a) -> int:
    root = library_root()
    data = read_index(root)
    by_kind: dict[str, int] = {}
    total = 0
    for it in data["items"]:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
        total += int(it.get("bytes") or 0)
    out = {
        "library": str(root),
        "items": len(data["items"]),
        "by_kind": by_kind,
        "size_mb": round(total / 1024 / 1024, 1),
        "unlicensed": sum(1 for it in data["items"] if it.get("license") in ("", None, "unknown")),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_scan(a) -> int:
    root = library_root()
    data = read_index(root)
    seen: dict[str, str] = {}
    dups = []
    for it in data["items"]:
        p = root / it["path"]
        if not p.exists():
            dups.append({"type": "missing", "id": it["id"]})
            continue
        seen.setdefault(it["sha256"], it["id"])
    print(json.dumps({"ok": True, "problems": dups}, ensure_ascii=False, indent=2))
    return 0


def cmd_prune(a) -> int:
    data = read_index(library_root())
    unused = [it for it in data["items"] if not it.get("used_in")]
    if a.json:
        print(json.dumps(unused, ensure_ascii=False, indent=2))
    else:
        print(f"[assets] 未被任何片子使用：{len(unused)} 个")
        for it in unused[:50]:
            print(f"  {it['id']}  {it.get('original_name')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="reelforge 素材库")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.set_defaults(fn=cmd_init)

    p = sub.add_parser("add")
    p.add_argument("path")
    p.add_argument("--type", choices=["image", "video", "audio", "font", "data", "file"])
    p.add_argument("--tags", default="")
    p.add_argument("--source", default="user", choices=["user", "generated", "downloaded"])
    p.add_argument("--license", default="unknown")
    p.add_argument("--origin", default="")
    p.add_argument("--note", default="")
    p.add_argument("--tag", default="", help="已存在时追加标签")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("search")
    p.add_argument("--query", default="")
    p.add_argument("--type", choices=["image", "video", "audio", "font", "data", "file"])
    p.add_argument("--tag", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("materialize")
    p.add_argument("--work", required=True)
    p.add_argument("--ids", default="")
    p.add_argument("--query", default="")
    p.add_argument("--tag", default="")
    p.add_argument("--to", default="")
    p.set_defaults(fn=cmd_materialize)

    p = sub.add_parser("stats"); p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("scan"); p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("prune")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_prune)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
