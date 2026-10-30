---
name: reelforge-duo
description: 双人模式的视频生产总控。人在前当总控（Antigravity 写稿 + Harness/Codex 执行），本 skill 给「执行 agent」用：负责建工作目录、给写稿 agent 生成交接稿、收稿后做参考度审计、卡验收门、驱动 wvp 出片。适用于「我用两个 agent 一起做一条视频」「我在电脑前，边看边推进」这类场景。不用于单 agent 一口气做完。
---

# ReelForge Duo（双人模式）

trio 模式里，总控可以由 WorkBuddy 这类 agent 担任（也可以一个 agent 全包）；双人模式里，**总控是你（人）**，
执行 agent 负责把所有判断题递给你，其余全部自己干完。

```
人（总控）─── 主题 / 拍板 / 验收
   │
   ├── 写稿 agent：Antigravity（只出稿）
   └── 执行 agent：你现在读的这个 skill（Harness / Codex / 任何能跑命令的）
```

trio 与 duo **共用同一套脚本和同一套门槛**，只是「谁来派活」不同：
- 三人模式：WorkBuddy 派活、轮询、把验收卡发到会话
- 双人模式：执行 agent 派活、直接问你、当面拿到你的「过」

## 怎么切

`config/pipeline.yaml` 里有 `mode: trio | duo`。当前 skill 只在 duo 模式下生效。

## 流程

| 步 | 谁做 | 动作 | 门 |
|---|---|---|---|
| 0 | 执行 | `duo.py start --work work/x --title "片名"` 建目录与状态 | — |
| 0.5 | 执行 | 检查 `personas.local.yaml`；没有就跑 `personas_init.py`，多轮确认后才落盘 | 🛑 你确认人设 |
| 1 | 执行 | `duo.py handoff --work work/x` 生成给写稿 agent 的交接稿 | — |
| 2 | 人 | 把交接稿粘给 Antigravity，它产出 `script.md` + `script.json`，放回 `work/x/` | — |
| 3 | 执行 | `duo.py intake --work work/x` → 相似度审计 → 超 60 就退回重写 | 🛑 你确认口播稿 |
| 3.5 | 执行 | 问路线 A/B、模板风格、配音方式/预设、字幕；写进 state | 🛑 你拍板 |
| 4 | 执行 | 按选定路线：A=wvp 章节/录屏；B=EAC film 时间轴 → 第 1 章/首段 | 🛑 你验收第 1 章 |
| 5 | 执行 | extract → 选定 TTS 预设合成 → 录屏 → 混音+字幕 | 🛑 你验收音频 |
| 6 | 执行 | ffprobe 验收 → 交付 | 🛑 你验收成片 |

**每一道门都要停下来问人**，别自己往下推。

## 0.5 人设与四问（每次开工都要做）

**人设不预设**。第一次部署先跑：

```bash
python <reelforge>/scripts/personas_init.py
```

- 问用户 1 个还是多个；逐个问 id / 显示名 / 定位 / 口吻 / 配音方式
- 汇总后让用户**输入默认人设名二次确认**，再确认写入；不确认不落盘
- 每次写稿前再问「这条用哪个人设」，**不要默认 ace**

**稿子确认后、进工程前**，当面问清四件事并写进 `state.json`：

| 问题 | 选项 |
|---|---|
| 路线 | A=HTML 渲染+录屏 / B=EAC `__seek(t)` 时间轴 |
| 模板/风格 | `eac_probe.py` 列出来给用户选；没装 EAC 就回 A |
| 配音 | IndexTTS 预设 / 参考干声 / edge-tts / 自定义 |
| 字幕 | 烧录 / 外挂 SRT / 不要 |


## 铁律：执行者不检索、不写稿

这是 duo 模式最容易出错的地方。分工是死的：

| 活 | 谁做 |
|---|---|
| 检索网页、读链接、抓资料、做取证 | **写稿 agent（Antigravity）** |
| 写口播稿、定分镜、写 `script.md` / `script.json` | **写稿 agent** |
| 建工程、写章节代码、配音、录屏、验收 | 你（执行者） |
| 拍板：主题、稿子、视觉方向、成片 | 人 |

**你手里没有 `script.md` 之前，一个字都不要写，更不要自己去搜网页。**
正确顺序永远是：

```
1. 生成交接稿（把用户给的链接全部写进去）
2. 停下来，把交接稿交给人 → 人粘给写稿 agent
3. 写稿 agent 交回：source_digest.md（检索结果）+ script.md + script.json + writer-notes.md
4. 你只做审计（参考度）与验收，工程、音频、录屏你来做
```

需要素材/事实/数据时，**不要自己搜**，写进交接稿让写稿 agent 一起带回来。
（例外：用户明确说「你自己查」时才自己检索，并在 `writer-notes.md` 里注明是你查的。）

如果你的环境里有模板库工具（例如 `eac_library_list` / `eac_template_read`），
**列模板是可以的**（这是工程侧资源），但画面内容仍然以写稿 agent 的分镜为准。

## 交接稿长什么样

`duo.py handoff` 产出 `handoff.writer.md`，内容是写稿 agent 需要的一切：
读哪些规则、人设、参考预算、**要检索的链接**、输出哪四个文件、越界了怎么自检。

四个产出文件：

| 文件 | 谁写 | 内容 |
|---|---|---|
| `source_digest.md` | 写稿 agent | 检索到的资料、关键事实、每个结论的出处 |
| `script.md` | 写稿 agent | 口播稿 |
| `script.json` | 写稿 agent | 机器读版本（拍数、画面描述） |
| `writer-notes.md` | 写稿 agent | 借鉴清单 + 自评参考度 + `writer-agent: <名字>` 标记 |

人只需要把它的内容整段粘给 Antigravity，再把 Antigravity 产出的
`script.md` / `script.json` 放回 `work/<slug>/`，然后执行 agent 接着走。

## 执行 agent 的边界

| 做 | 不做 |
|---|---|
| 建目录、跑脚本、发交接稿、审参考度、驱动 wvp | 不自己写稿（要改稿就退回给写稿 agent） |
| 改代码、写章节、配音、录屏、验收 | 不替你做审美决定（主题、配色、节奏要问你） |
| 每道门停下来问你 | 不跳过门、不自我批准 |

## Codex / 其他 CLI 执行者

- 装 skill 到对应目录（`~/.codex/skills/`、`~/.dsh/skills/`），或在项目 `AGENTS.md` 里引用本文件
- 没有 MCP 也能用：所有步骤都是本地脚本 + 文本粘贴
- Windows 用 Git Bash 执行 `sh`；Python 脚本直接 `python scripts/xxx.py`

## 参考

| 文件 | 何时读 |
|---|---|
| `references/duo-protocol.md` | 每次开工前：人机分工、验收话术、异常处理 |
| `references/executor-notes.md` | Harness / Codex 各自的差异与坑 |
| 总控 `references/script-contract.md` | 审稿时 |
| 总控 `references/wvp-handoff.md` | 出片阶段 |
| 总控 `references/asset-library.md` | 需要素材时 |
