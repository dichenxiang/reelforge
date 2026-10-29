"""reelforge 状态机：三端（总控 / 写稿 / 执行）共用一份 work/<slug>/state.json。

    python state.py init --work work/demo --title "GPT-6 测评"
    python state.py set  --work work/demo --stage script --status running --job writer=conv_123
    python state.py gate --work work/demo --name script_gate --artifacts work/demo/script.md
    python state.py approve --work work/demo --gate script_gate --note "稿子可以"
    python state.py show --work work/demo
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STAGES = ["intake", "reference", "script", "script_gate", "build",
          "audio_gate", "record", "qa", "deliver", "done"]
STATUS = ["running", "awaiting_user", "blocked", "approved", "done"]
GATES = {"script_gate": "口播稿确认", "audio_gate": "音频确认",
         "chapter_gate": "第 1 章验收", "final_gate": "成片验收"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def path_of(work: str | Path) -> Path:
    return Path(work) / "state.json"


def load(work: str | Path) -> dict:
    p = path_of(work)
    if not p.exists():
        raise SystemExit(f"[state] 没有状态文件：{p}\n        先跑 python state.py init --work {work}")
    return json.loads(p.read_text(encoding="utf-8"))


def save(work: str | Path, st: dict) -> None:
    st["updated_at"] = now()
    path_of(work).write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event(st: dict, kind: str, **kw) -> None:
    st.setdefault("history", []).append({"at": now(), "event": kind, **kw})


def cmd_init(a) -> int:
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    p = path_of(work)
    if p.exists() and not a.force:
        raise SystemExit(f"[state] 已存在：{p}（要重建加 --force）")
    st = {
        "slug": work.name,
        "title": a.title or work.name,
        "stage": "intake",
        "status": "running",
        "gate": None,
        "owner": "workbuddy",
        "jobs": {},
        "artifacts": [],
        "audit": {},
        "history": [],
        "created_at": now(),
        "updated_at": now(),
    }
    event(st, "init")
    save(work, st)
    print(json.dumps({"ok": True, "state": str(p)}, ensure_ascii=False))
    return 0


def cmd_set(a) -> int:
    st = load(a.work)
    if a.stage:
        if a.stage not in STAGES:
            raise SystemExit(f"[state] stage 必须是 {STAGES}")
        st["stage"] = a.stage
    if a.status:
        if a.status not in STATUS:
            raise SystemExit(f"[state] status 必须是 {STATUS}")
        st["status"] = a.status
    if a.owner:
        st["owner"] = a.owner
    for kv in a.job or []:
        k, _, v = kv.partition("=")
        st.setdefault("jobs", {})[k] = v
    for art in a.artifacts or []:
        if art not in st["artifacts"]:
            st["artifacts"].append(art)
    event(st, "set", stage=st["stage"], status=st["status"], by=a.by or st.get("owner"))
    save(a.work, st)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def cmd_gate(a) -> int:
    st = load(a.work)
    if a.name not in GATES:
        raise SystemExit(f"[state] gate 必须是 {list(GATES)}")
    st["stage"] = a.name
    st["status"] = "awaiting_user"
    st["gate"] = a.name
    st["gate_label"] = GATES[a.name]
    for art in a.artifacts or []:
        if art not in st["artifacts"]:
            st["artifacts"].append(art)
    event(st, "gate", gate=a.name)
    save(a.work, st)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def cmd_approve(a) -> int:
    st = load(a.work)
    if st.get("gate") != a.gate:
        raise SystemExit(f"[state] 当前 gate 是 {st.get('gate')}，不是 {a.gate}")
    st["status"] = "approved"
    st["gate_note"] = a.note or ""
    st["approved_at"] = now()
    event(st, "approve", gate=a.gate, note=a.note or "")
    save(a.work, st)
    print(json.dumps({"ok": True, "gate": a.gate, "status": st["status"]}, ensure_ascii=False))
    return 0


def cmd_show(a) -> int:
    st = load(a.work)
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    print(f"{st['slug']} · {st.get('title','')}")
    print(f"  stage={st['stage']}  status={st['status']}  gate={st.get('gate') or '-'}")
    jobs = st.get("jobs") or {}
    if jobs:
        print("  jobs: " + ", ".join(f"{k}={v}" for k, v in jobs.items()))
    if st.get("artifacts"):
        print("  artifacts:")
        for x in st["artifacts"][-6:]:
            print(f"    - {x}")
    last = (st.get("history") or [])[-1:]
    if last:
        print(f"  last: {last[0]['event']} @ {last[0]['at']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="reelforge 状态机")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--work", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("set")
    p.add_argument("--work", required=True)
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--status", choices=STATUS)
    p.add_argument("--owner")
    p.add_argument("--job", action="append", help="agent=id，可多次")
    p.add_argument("--artifacts", action="append")
    p.add_argument("--by")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("gate")
    p.add_argument("--work", required=True)
    p.add_argument("--name", required=True, choices=list(GATES))
    p.add_argument("--artifacts", action="append")
    p.set_defaults(fn=cmd_gate)

    p = sub.add_parser("approve")
    p.add_argument("--work", required=True)
    p.add_argument("--gate", required=True, choices=list(GATES))
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("show")
    p.add_argument("--work", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_show)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
