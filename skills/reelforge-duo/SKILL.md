---
name: reelforge-duo
description: 双人模式的视频生产总控。人在前当总控（Antigravity 写稿 + Harness/Codex 执行），本 skill 给「执行 agent」用：负责建工作目录、给写稿 agent 生成交接稿、收稿后做参考度审计、卡验收门、驱动 wvp 出片。适用于「我用两个 agent 一起做一条视频」「我在电脑前，边看边推进」这类场景。不用于单 agent 一口气做完。
---

# ReelForge Duo（双人模式）

三 agent 模式里，总控是 WorkBuddy；双人模式里，**总控是你（人）**，
执行 agent 负责把所有判断题递给你，其余全部自己干完。

```
人（总控）─── 主题 / 拍板 / 验收
   │
   ├── 写稿 agent：Antigravity（只出稿）
   └── 执行 agent：你现在读的这个 skill（Harness / Codex / 任何能跑命令的）
```

三 agent 模式与双人模式**共用同一套脚本和同一套门槛**，只是「谁来派活」不同：
- 三人模式：WorkBuddy 派活、轮询、把验收卡发到会话
- 双人模式：执行 agent 派活、直接问你、当面拿到你的「过」

## 怎么切

`config/pipeline.yaml` 里有 `mode: trio | duo`。当前 skill 只在 duo 模式下生效。

## 流程

| 步 | 谁做 | 动作 | 门 |
|---|---|---|---|
| 0 | 执行 | `duo.py start --work work/x --title "片名"` 建目录与状态 | — |
| 1 | 执行 | `duo.py handoff --work work/x` 生成给写稿 agent 的交接稿 | — |
| 2 | 人 | 把交接稿粘给 Antigravity，它产出 `script.md` + `script.json`，放回 `work/x/` | — |
| 3 | 执行 | `duo.py intake --work work/x` → 相似度审计 → 超 60 就退回重写 | 🛑 你确认口播稿 |
| 4 | 执行 | `make_wvp_inputs.py` → scaffold → 第 1 章 → 其余章 | 🛑 你验收第 1 章 |
| 5 | 执行 | extract → IndexTTS 合成 → 录屏 | 🛑 你验收音频 |
| 6 | 执行 | ffprobe 验收 → 交付 | 🛑 你验收成片 |

**每一道门都要停下来问人**，别自己往下推。

## 交接稿长什么样

`duo.py handoff` 产出 `handoff.writer.md`，内容是写稿 agent 需要的一切：
读哪些规则、人设、参考预算、输出哪三个文件、越界了怎么自检。

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
