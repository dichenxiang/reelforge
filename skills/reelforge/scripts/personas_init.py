"""personas_init.py —— 第一次部署时，引导用户建立自己的口播人设（1 个或多个）。

设计原则：
- **不预设“阿测 / 把关学长”**，那是示例；这里从零问。
- **多重确认**：汇总 → 输入默认人设名 → 再确认写入，避免手滑把半成品写进本地。
- 人设数量 1..N，默认人设必须存在。
- 只写 `config/personas.local.yaml`（已 gitignore），不碰仓库里的 example。

交互：
    python scripts/personas_init.py
非交互（CI / 自动化）：
    python scripts/personas_init.py --from-json my-personas.json --yes
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
CONFIG = SKILL / "config"
LOCAL = CONFIG / "personas.local.yaml"

EDGE_VOICES = [
    ("zh-CN-YunxiNeural", "青年男声，清晰偏快"),
    ("zh-CN-YunjianNeural", "沉稳男声，偏慢"),
    ("zh-CN-YunyangNeural", "新闻播报男声"),
    ("zh-CN-XiaoxiaoNeural", "温暖女声"),
    ("zh-CN-XiaoyiNeural", "活泼女声"),
]


def ask(prompt: str, default: str = "") -> str:
    tip = f"{prompt}" + (f" [{default}]" if default else "") + "："
    val = input(tip).strip()
    return val or default


def ask_choice(prompt: str, options: list[str], default: str) -> str:
    print(prompt)
    for i, o in enumerate(options, 1):
        print(f"  {i}) {o}")
    val = input(f"选择 1-{len(options)} [{default}]：").strip() or default
    if val.isdigit() and 1 <= int(val) <= len(options):
        return options[int(val) - 1]
    return val if val in options else default


def build_one(idx: int, total: int) -> dict:
    print(f"\n—— 第 {idx}/{total} 个人设 ——")
    pid = ask("内部 id（英文小写，如 host / senior / xiaowang）", "host" if idx == 1 else f"persona{idx}")
    display = ask("显示名（片子里/字幕里的人设称呼）", "主讲人" if idx == 1 else pid)
    positioning = ask("一句话定位（他是谁、站谁那边）", "一个把复杂东西讲清楚的过来人")
    tone = ask("说话风格（短句/先结论/爱对比/护小白…）", "短句、先给结论、少形容词")
    banned = ask("禁词（逗号分隔，可空）", "")

    provider = ask_choice("配音方式：", ["edge", "indextts", "custom"], "edge")
    voice: dict = {"provider": provider}
    if provider == "edge":
        names = [v[0] for v in EDGE_VOICES]
        print("可选 edge 音色：")
        for n, d in EDGE_VOICES:
            print(f"  - {n}  {d}")
        voice["voice"] = ask("音色名", "zh-CN-YunxiNeural")
        voice["rate"] = ask("语速（如 +8% / -4%）", "+0%")
        voice["pitch"] = ask("音高（如 +0Hz）", "+0Hz")
    elif provider == "indextts":
        voice["ref_audio"] = ask("参考音频绝对路径（10–20 秒干声）", "")
        voice["preset"] = ask("IndexTTS 预设名（可空，填写后优先用预设）", "")
    else:
        voice["cmd"] = ask("自定义命令模板（{text} {out} {voice} 占位）", "")

    return {
        "id": pid,
        "display_name": display,
        "positioning": positioning,
        "personality": [tone],
        "banned": [b.strip() for b in banned.split(",") if b.strip()],
        "voice": voice,
        "prompt_block": f"你是「{display}」，{positioning}。说话：{tone}。",
    }


def summarize(data: dict) -> None:
    print("\n========== 确认清单 ==========")
    for p in data["personas"]:
        v = p.get("voice") or {}
        print(f"- {p['id']} / {p['display_name']}（{p['positioning']}）")
        print(f"    配音：{v.get('provider')} {v.get('preset') or v.get('voice') or v.get('ref_audio') or ''}")
        if p.get("banned"):
            print(f"    禁词：{'、'.join(p['banned'])}")
    print(f"默认人设：{data['default_persona']}")
    print("==============================")


def confirm(data: dict) -> bool:
    summarize(data)
    if ask("以上信息正确吗？(y/N)", "n").lower() != "y":
        return False
    default = data["default_persona"]
    display = next(p["display_name"] for p in data["personas"] if p["id"] == default)
    typed = ask(f"请输入默认人设的显示名「{display}」以确认", "")
    if typed != display:
        print("不一致，已取消（没有写入任何文件）。")
        return False
    if ask("写入本地 personas.local.yaml？(yes/N)", "n").lower() != "yes":
        print("已取消。")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", default="", help="已有 JSON 时直接导入（结构同输出）")
    ap.add_argument("--yes", action="store_true", help="跳过交互确认（CI 用）")
    a = ap.parse_args()

    if LOCAL.exists() and not a.from_json:
        print(f"已存在本地人设：{LOCAL}\n（覆盖会先备份为 .bak-时间戳）")
        if ask("要重新配置吗？(y/N)", "n").lower() != "y":
            print("保留现有配置。")
            return 0

    if a.from_json:
        data = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
    else:
        n = ask("你要配置几个人设？（1 个主讲人也可以）", "1")
        n = max(1, int(n)) if str(n).isdigit() else 1
        people = [build_one(i + 1, n) for i in range(n)]
        ids = [p["id"] for p in people]
        default = ask(f"默认用哪个人设？可选 {ids}", ids[0])
        if default not in ids:
            default = ids[0]
        data = {"version": 1, "default_persona": default, "personas": people}

        if not a.yes:
            if not confirm(data):
                return 1

    # 归一化：list 形式转成 {id: persona}（personas.py 只认 dict）
    if isinstance(data.get("personas"), list):
        data["personas"] = {p["id"]: p for p in data["personas"]}

    # 校验
    ids = list(data["personas"].keys())
    if len(set(ids)) != len(ids):
        raise SystemExit("[personas] id 重复")
    if data.get("default_persona") not in ids:
        raise SystemExit("[personas] default_persona 不在列表里")

    if LOCAL.exists() and not a.yes:
        bak = LOCAL.with_suffix(".yaml.bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(LOCAL, bak)
        print(f"已备份：{bak}")

    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\n[OK] 写入 {LOCAL}")
    print(f"  默认人设：{data['default_persona']}")
    print("  下一步：python scripts/personas.py --list 检查；写稿时用 --persona 指定")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
