"""生成给写稿 / 执行 agent 的任务包（markdown，可直接贴进会话或落盘让它读）。

    python pack_task.py writer --work work/demo --persona ace --budget 40
    python pack_task.py runner --work work/demo --theme blueprint --mode A --persona ace

任务包只写“做什么 + 读哪个文件 + 产出什么 + 什么时候停”，
具体方法论在各自的 skill 里，避免 prompt 越写越长。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL.parent


def common(work: Path) -> str:
    return f"""- 工作目录：{work.resolve()}
- 状态文件：{work / 'state.json'}（每步更新，见下方命令）
- 总控 skill：{SKILL}
"""


def pattern_file(persona: str) -> Path:
    """按人设选「本号文案套路」文件（从真实视频逆向出来的）。"""
    name = "patterns-ace.md" if persona == "ace" else "patterns-gatekeeper.md"
    return SKILLS_ROOT / "reelforge-writer" / "references" / name


def persona_block(persona: str) -> str:
    """把账号人设段落直接嵌进任务包——写稿 agent 不用自己找。"""
    script = SKILL / "scripts" / "personas.py"
    try:
        out = subprocess.run(
            [sys.executable, str(script), "--prompt", persona],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        ).stdout.strip()
    except Exception as e:  # pragma: no cover
        out = ""
    if not out:
        out = f"（读不到人设，请自己执行：python {script} --prompt {persona}）"
    return out


def writer_pack(a) -> str:
    work = Path(a.work).resolve()
    ref = (work / "reference.json")
    budget = f"""- 参考度目标 {a.budget} 分，硬上限 60 分（`similarity.py` 会验）
- 有参考时：结构可借、手法 ≤2 个，**文案必须原创**
""" if ref.exists() or a.reference else "- 参考稿只提供写法；内容必须原创，不得抄原句（结构相似度会算分）\n"
    persona = persona_block(a.persona)

    return f"""# 任务：写口播稿（reelforge-writer）

你是写稿 agent。**只写稿，不写代码、不搭工程。**

## 环境
{common(work)}- 你的 skill：{SKILLS_ROOT / 'reelforge-writer'}
- 人设：{a.persona}（人设段落已经贴在下面，**照这个口吻写**）
- 素材库清单：{work / 'assets.json'}（有就参考已有素材，不要重复找图）

## 必读（按顺序，第 1、2 项是权威）

1. **{SKILL / 'vendor' / 'web-video-presentation' / 'references' / 'SCRIPT-STYLE.md'}**
   ← **口播怎么写，唯一权威。全文读，别复述、别改写、别另立规则**
2. **{SKILL / 'vendor' / 'web-video-presentation' / 'references' / 'OUTLINE-FORMAT.md'}**
   ← outline.md 的格式规范
3. **{pattern_file(a.persona)}** ← **本号真实文案套路（从真实视频逆向），照这个写**
4. {SKILLS_ROOT / 'reelforge-writer' / 'SKILL.md'}
5. {SKILLS_ROOT / 'reelforge-writer' / 'references' / 'writing-rules.md'}（本项目额外 4 条约束）
6. **{SKILLS_ROOT / 'humanizer-zh' / 'SKILL.md'}** ← **第 ② 步用（去 AI 味，已装）**
   （边界说明：{SKILLS_ROOT / 'reelforge-writer' / 'references' / 'humanizer-zh.md'}）
7. 参考证据（有参考时）：{ref if ref.exists() else '（无）'}
8. 拆解报告：{work / 'evidence.md'}（有就读）

## 账号人设（照这个写，禁词不许出现）

{persona}

## 先检索，再写稿（硬性顺序）

如果给了链接或需要事实/数据，**先检索取证**：

1. 逐条打开链接，抓正文与关键信息
2. 把事实、来源、原文片段写进 `source_digest.md`（每个结论标出处）
3. 抓不到或互相矛盾的，写「未证实 / 有冲突」，**不许编**
4. 检索完再进入写稿；不要一边搜一边编稿

## 长度：不要预设，按内容走

- **时长由内容决定**，不为凑时长注水，也不为压时长删信息（信息保留 ≥60% 是硬约束）
- 骨架按套路文件走：信息讲完就收，天然短的可以是 30 秒，天然长的可以十几分钟
- 内容超过一章就分章，`outline.md` 里出章节表（每章时长、全片起点、衔接方式），wvp 逐章构建
- `script.json` 的 `duration_sec` 按写完的实际稿子估（中文约 5 字/秒），不要反过来先定时长再凑稿

## 风格听谁的（重要）

**口播风格、节奏、句式、留白，全部按 SCRIPT-STYLE.md。**
不要按你自己的习惯写，不要模仿别的账号，不要把书面语改短了就算口播。
写完必须按它的三层自检走：形式层 → 风骨层 → **念出来测试**（念不顺就重写）。

## 约束（本项目只加这四条）
- 画幅 16:9，单段 ≤14 个汉字上屏，口播 5 字/秒估算
{budget}- 不许出现「全网最强 / 第一 / 必买」这类词
- 不许抄参考片的句子；结构相似度会算分

## 收尾四步（顺序固定，不许跳）

| 步 | 做什么 | 权威来源 |
|---|---|---|
| ① 三层自检 | 形式层 → 风骨层 → **念出来测试**，按 fail 项改稿 | SCRIPT-STYLE.md |
| ② 去 AI 味清洗 | 只洗句子层，不动结构 | humanizer-zh（已装） |
| ③ 写规划与结构 | outline.md + script.json | OUTLINE-FORMAT.md / script-contract |
| ④ 参考度审计 | 结构 + 文案重合，超线就重写结构 | similarity.py |

① 的做法：形式层对照 SCRIPT-STYLE.md 的 8 条原则 → 风骨层对照去 AI 味五类（最重要）
→ 念出来测试（终极标准）：逐句念，念不顺就改。
有 Agent Teams 就开一个 reviewer agent 审这三层；没有就自己严格逐项核查。拿到结论先改稿。

② 的指令（必须原样转达，否则会毁掉口播稿）：

> 只改句子层面的 AI 痕迹。保留 `---` 分节拍、保留每拍的口语节奏、不要合并节拍、
> 不要改数字和结论、不要补充原文没有的信息、不要把「可能」改成「确定」。
> 改完自己念一遍，念不顺就还原。

② 之后不再改结构；清洗把节奏弄乱了以清洗前为准。

## 产出（全部落在工作目录）
- `source_digest.md`：检索到的资料与出处（抓不到的如实写「未证实」，不许编）
- `script.md`：口播稿，按 `---` 切节拍（节拍数 = beats 数）
- `outline.md`：开发计划，**按 OUTLINE-FORMAT.md 写**（章节、每步屏幕内容、信息池、素材清单）
- `script.json`：契约见 {SKILL / 'references' / 'script-contract.md'}
- `writer-notes.md`：借了什么结构、放弃了什么、自评参考度；
  **第一行必须写 `writer-agent: <你的名字/型号>`**（校验稿子确实出自写稿 agent），
  再写一行 `humanizer: on/off`（第 ② 步做了没有）

## 收尾（必须做）
1. 四步收尾全部走完（① 三层自检 → ② 去 AI 味清洗 → ③ outline/json → ④ 审计）
2. 跑审计：
```
python {SKILL / 'scripts' / 'similarity.py'} --work "{work}" --target {a.budget} --max 60
```
- 通过 → `python {SKILL / 'scripts' / 'state.py'} set --work "{work}" --stage script --status awaiting_user --owner writer`
- 不通过 → 按 hint 重写，不要只换同义词

最后用 5 行以内汇报：标题、拍数、预估时长、自评参考度、需要用户确认的点。
"""


def runner_pack(a) -> str:
    work = Path(a.work).resolve()
    return f"""# 任务：按 wvp 流程出片（reelforge-runner）

你是执行 agent。**只做工程与音频，不改稿、不做审美决策。**

## 环境
{common(work)}- 你的 skill：{SKILLS_ROOT / 'reelforge-runner'}
- wvp：{SKILL / 'vendor' / 'web-video-presentation'}
- 稿子：{work / 'script.md'}
- outline：{work / 'outline.md'}
- 素材清单：{work / 'assets.json'}

## 必读（按顺序）
1. {SKILLS_ROOT / 'reelforge-runner' / 'SKILL.md'}
2. {SKILL / 'vendor' / 'web-video-presentation' / 'SKILL.md'}（Phase 2–4）
3. {SKILL / 'vendor' / 'web-video-presentation' / 'references' / 'CHAPTER-CRAFT.md'}

## 参数
- 主题：{a.theme or '按 outline 推荐'}
- 开发模式：{a.mode}（第 1 章必须单 agent 做完并停下）
- 人设音色：{a.persona}
- 并行：{'用 /agent-teams，第 2..N 章每章一个 task' if a.team else '不开团队'}

## 阶段与停止点
1. scaffold + 素材投放（`python {SKILL / 'scripts' / 'assets.py'} materialize --work "{work}"`）
2. 第 1 章做完 → **停**，写 `state.py gate --name chapter_gate`
3. 用户确认后，第 2..N 章（可并行）
4. `npm run extract-narrations` → `PRESENTATION_TTS=indextts npm run synthesize-audio`
5. 音频完成 → **停**，写 `state.py gate --name audio_gate`
6. 录屏（人工或 `record.mjs`）→ ffprobe 验收 → `state.py set --stage qa --status done`

## 禁止
- 改 `script.md` / `narrations.ts` 的文案（要改先回总控）
- 换主题、换画幅、改 wvp 源码
- 没验收就往下走

汇报格式：当前阶段、产物路径、ffprobe 结果（如有）、下一步等谁。
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("writer")
    p.add_argument("--work", required=True)
    p.add_argument("--persona", default="ace")
    p.add_argument("--budget", type=int, default=40)
    p.add_argument("--reference", action="store_true")
    p.set_defaults(fn=lambda a: writer_pack(a))

    p = sub.add_parser("runner")
    p.add_argument("--work", required=True)
    p.add_argument("--theme", default="")
    p.add_argument("--mode", default="A", choices=["A", "B", "C"])
    p.add_argument("--persona", default="ace")
    p.add_argument("--team", action="store_true")
    p.set_defaults(fn=lambda a: runner_pack(a))

    a = ap.parse_args()
    work = Path(a.work)
    (work / "tasks").mkdir(parents=True, exist_ok=True)
    name = "writer.md" if a.cmd == "writer" else "runner.md"
    out = work / "tasks" / name
    out.write_text(a.fn(a), encoding="utf-8")
    print(json.dumps({"ok": True, "task": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
