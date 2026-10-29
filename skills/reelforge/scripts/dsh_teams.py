"""检查 / 安装 DeepSeek Harness 的 AgentTeams 插件到指定 profile。

为什么需要它：
- 桌面 profile 一般由桌面端自带插件；但 **MCP 走的是 headless profile**
- headless 默认没有 agent-teams → 我们让 dsh 跑 `/agent-teams` 时其实没有团队能力，
  章节并行会静默退化成顺序执行
- headless 没有 UI，团队创建必须传 `approval="automatic"`，否则会卡在审批面板

    python dsh_teams.py --status              # 只看状态
    python dsh_teams.py --install headless    # 把插件装到 headless profile
    python dsh_teams.py --install all         # 所有缺插件的 profile
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

PKG = "@nanmicoder/dsh-agent-teams"
PROFILES = ["headless", "web", "desktop"]


def dsh_home() -> Path:
    env = os.environ.get("DSH_HOME")
    return Path(env).expanduser() if env else Path.home() / ".dsh"


def profile_dir(root: Path, name: str) -> Path:
    return root / "profiles" / name


def has_plugin(prof: Path) -> bool:
    pj = prof / "package.json"
    if not pj.exists():
        return False
    try:
        d = json.loads(pj.read_text(encoding="utf-8"))
    except Exception:
        return False
    bundles = (d.get("dsh", {}).get("profile", {}) or {}).get("bundles") or []
    return PKG in bundles


def plugin_dir(prof: Path) -> Path | None:
    p = prof / "node_modules" / "@nanmicoder" / "dsh-agent-teams"
    return p if (p / "package.json").exists() else None


def find_source(root: Path) -> tuple[Path | None, str | None]:
    for name in PROFILES:
        prof = profile_dir(root, name)
        d = plugin_dir(prof)
        if d:
            return d, name
    return None, None


def install_to(root: Path, name: str, src: Path) -> tuple[bool, str]:
    prof = profile_dir(root, name)
    if not prof.exists():
        return False, f"profile 不存在：{prof}"
    dst = prof / "node_modules" / "@nanmicoder" / "dsh-agent-teams"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
    except Exception as e:
        return False, f"复制失败：{e}"
    pj = prof / "package.json"
    try:
        d = json.loads(pj.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"package.json 读取失败：{e}"
    prof_cfg = d.setdefault("dsh", {}).setdefault("profile", {})
    bundles = prof_cfg.get("bundles") or []
    if PKG not in bundles:
        bundles.append(PKG)
    prof_cfg["bundles"] = bundles
    deps = d.setdefault("dependencies", {})
    try:
        ver = json.loads((src / "package.json").read_text(encoding="utf-8")).get("version", "0.1.27")
    except Exception:
        ver = "0.1.27"
    deps[PKG] = ver
    pj.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True, f"已装 {ver} → {dst}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--install", choices=PROFILES + ["all"])
    a = ap.parse_args()

    root = dsh_home()
    print(f"[teams] DSH_HOME = {root}")
    src, src_name = find_source(root)
    print(f"[teams] 插件来源：{src if src else '（本机没找到，先用桌面端装一次）'}"
          f"{'（来自 ' + src_name + ' profile）' if src_name else ''}")

    status = []
    for name in PROFILES:
        prof = profile_dir(root, name)
        if not prof.exists():
            status.append((name, "无该 profile", False))
            continue
        status.append((name, "已开启" if has_plugin(prof) else "未开启", has_plugin(prof)))
    for name, note, ok in status:
        print(f"  {name:<9} {note}")

    if a.install:
        if not src:
            print("[teams] 没有可复制的插件目录。先在桌面端装一次："
                  "\n        dsh plugin --profile desktop add github:NanmiCoder/dsh-agent-teams")
            return 2
        targets = PROFILES if a.install == "all" else [a.install]
        for t in targets:
            prof = profile_dir(root, t)
            if not prof.exists():
                print(f"[teams] {t}: profile 不存在，跳过")
                continue
            ok, msg = install_to(root, t, src)
            print(f"[teams] {t}: {msg}")
        print("\n[teams] 装完要重启该 profile 的 Harness 进程才生效。")
        print("[teams] 另外：headless 没有 UI，建团队时必须用 approval=\"automatic\"，"
              "否则会卡在审批面板。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
