# 执行者差异说明

双人模式里「执行 agent」可以是不同东西，流程一样，细节有别。

## DeepSeek Harness

| 项 | 说明 |
|---|---|
| 怎么用 | MCP `mcp__deepseek-harness__start` / `result`；或自己跑 `dsh --profile headless` |
| 会话可见 | 用 `session_workspace="default"`，会话开在 DSH 桌面端「默认工作区」，界面里能看到实时过程 |
| skill 位置 | `~/.dsh/skills/reelforge-runner`、`~/.dsh/skills/reelforge-duo` |
| 并行 | 装了 `dsh-agent-teams` 就能 `/agent-teams` 并行第 2..N 章 |
| 坑 | 模型来源分三种，默认官方；官方 V4.1 Flash 的 id 是 `deepseek-flash` |

## Codex CLI

| 项 | 说明 |
|---|---|
| 怎么用 | 直接在 Codex 会话里说「按 reelforge-duo 走」；Codex 自己能跑 shell |
| skill 位置 | `~/.codex/skills/reelforge-duo`（装不了就写进项目 `AGENTS.md`） |
| 会话可见 | Codex 自己的会话界面，不用管 |
| 并行 | Codex 支持 subagent，章节可以分给不同 subagent |
| 坑 | Windows 上 `sh` 要用 Git Bash；Python 用 `python`，别用 `python3` |

## 其他 CLI agent（Claude Code / Aider / OpenCode 等）

照 Codex 那栏走即可：**只要能读文件、能执行命令、能改文件，就能当执行者**。

## 最小安装（任意执行者）

```bash
# 1) 三个 skill（总控脚本 + 写稿 + 执行）
bash install.sh --workbuddy          # 或 --dsh / --codex / --claude
# 2) 让 agent 知道要做什么：在项目里放一句
echo "视频任务先读 ~/.workbuddy/skills/reelforge-duo/SKILL.md" >> AGENTS.md
```

## 共同约定

- 项目目录一律用**绝对路径**，不要依赖 cwd
- 所有脚本调用：`python <绝对路径>/scripts/xxx.py`
- 每完成一个阶段：`python duo.py gate --work <work> --name <gate>` 停下来问人
- 产物只写进 `work/`，不要写回 skill 目录
