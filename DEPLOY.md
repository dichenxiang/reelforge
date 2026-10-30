# 部署说明

> 想让 AI 自动部署？把仓库地址发给它并说「读 `AGENT_DEPLOY.md`，按步骤部署」。
> 本文件是人读的背景与原理；`AGENT_DEPLOY.md` 是给 agent 执行的手册。


ReelForge 把短视频生产拆成三部分（总控 / 写稿 / 执行）——这是**职责边界**，不是必须三个 agent；单 agent 全包也可以。**角色和具体产品解耦**：
你可以用 WorkBuddy + Antigravity + DeepSeek Harness（默认组合），
也可以换成 Claude Code + 任意写作模型 + Codex，只要满足角色能力。

## 1. 三部分职责

| 角色 | 能力要求 | 默认实现 | 用什么 skill |
|---|---|---|---|
| 总控 | 能读写文件、能发消息给另外两个、能等结果 | WorkBuddy | `reelforge` |
| 写稿 | 强写作、能读文件、能写文件 | Antigravity（Gemini 4 Argon Medium，低思考） | `reelforge-writer` |
| 执行 | 能执行 shell、改代码、跑 node/python | DeepSeek Harness（官方来源，`deepseek-flash`＝V4.1 Flash，max 思考） | `reelforge-runner` |

出图是可选能力，谁有谁做（Antigravity / ImageGen / 人工）。

## 2. 依赖

| 依赖 | 版本 | 谁需要 | 说明 |
|---|---|---|---|
| Python | 3.10+ | 总控 / 执行 | 跑 `scripts/*.py` |
| Node.js | 18+ | 执行 | wvp 的 Vite + React 工程 |
| jq | 1.6+ | 执行 | wvp 音频 runner 解析 json |
| ffmpeg + ffprobe | 6.x | 执行 | 录屏转码、音频拼接、验收 |
| git | 任意 | 安装 | 拉 wvp |
| IndexTTS | 可选 | 执行 | 本地克隆音色；没有就用 edge-tts |
| DSH agent-teams | 可选 | 执行 | 章节并行；没有就顺序做 |

Windows 上还需要 Git Bash（`sh`）。

## 3. 三步安装

```bash
git clone https://github.com/<you>/reelforge.git
cd reelforge

# 1) 装 skill 到各 agent 的目录（按你实际有的 agent 选）
bash install.sh --workbuddy --antigravity --dsh

# 2) 拉 wvp（不随仓库分发，保持上游版本）
bash install.sh --with-wvp

# 3) 自检
python skills/reelforge/scripts/probe.py
```

`install.sh --help` 看全部参数（也支持 `--claude`、`--codex`、`--all`）。

## 4. 默认组合：WorkBuddy + Antigravity + DeepSeek Harness

### 4.1 Skill 放哪

| Skill | 目录 |
|---|---|
| `reelforge` | `~/.workbuddy/skills/reelforge` |
| `reelforge-writer` | `~/.gemini/antigravity/skills/reelforge-writer` |
| `reelforge-runner` | `~/.dsh/skills/reelforge-runner` |

写稿 skill 也建议在 WorkBuddy 留一份，方便总控自己校对；
执行 skill 在 WorkBuddy 留一份，方便人工兜底。

### 4.2 MCP 配置

把 `mcp/antigravity` 和 `mcp/deepseek-harness` 放到固定位置（例如 `~/.reelforge/mcp/`），
在 `~/.workbuddy/mcp.json` 里加：

```json
{
  "mcpServers": {
    "antigravity": {
      "command": "python",
      "args": ["C:/Users/<you>/.reelforge/mcp/antigravity/server.py"]
    },
    "deepseek-harness": {
      "command": "python",
      "args": ["C:/Users/<you>/.reelforge/mcp/deepseek-harness/server.py"]
    }
  }
}
```

两个桥接都是 **MCP over stdio**，不监听端口，不需要额外鉴权。
它们分别调用本机的 Antigravity CLI（`language_server.exe`）和 DSH（`cli.js`），
所以两个桌面应用必须先登录、保持可运行。

### 4.3 Antigravity 用 Gemini 4 Argon

桥接默认只暴露 `flash` / `flash_lite` / `pro` 三档，而 Antigravity 实际支持
`gemini-4-argon-low|medium|high`。两种做法：

**A. 改桥接（推荐）**

编辑 `mcp/antigravity/server.py`，把 `model` 的 enum 改成：

```python
"enum": ["flash", "flash_lite", "pro",
         "gemini-4-argon-low", "gemini-4-argon-medium", "gemini-4-argon-high"]
```

然后重启 WorkBuddy。之后 `start_session(model="gemini-4-argon-medium")` 即可。

**B. 不改桥接**

在 Antigravity 桌面里手动把默认模型切到 Argon Medium，桥接传 `pro` 时按
应用当前选择执行（不同版本行为可能不同，以实测为准）。

### 4.4 模型来源（provider）

Harness 里有多套来源，MCP 用 `provider` 参数选，**默认官方**：

| provider | 来源 | 模型 id（部分） | 计费 |
|---|---|---|---|
| `deepseek-account` | DeepSeek 官方账号 | `deepseek-flash`（V4.1 Flash）、`deepseek-v4-pro` | 官方额度 |
| `workbuddy` | WorkBuddy 国内版 | `deepseek-v4.1-flash`、`glm-5.3`、`kimi-k3.1-pro`、`hy3`… | 积分倍率 |
| `workbuddy-global` | WorkBuddy 国际版 | `fast-model`、`balanced-model`、`primary-model`、`hy4-preview`… | 积分倍率 |

注意：**官方 API 里 V4.1 Flash 的 id 是 `deepseek-flash`**，`deepseek-v4.1-flash`
只在 WorkBuddy 来源可用——写错会被官方拒绝。

默认配置：`provider=deepseek-account`、`model=deepseek-flash`、`reasoning_effort=max`。

想切 WorkBuddy 来源：headless profile 也要装插件（桌面端装了不代表 headless 有）：

```bash
dsh plugin --profile headless add dsh-connect-workbuddy
```

然后调用时传 `provider="workbuddy"` / `"workbuddy-global"`。

### 4.5 AgentTeams 与沙箱（并行开发必读）

```bash
python skills/reelforge/scripts/dsh_teams.py --status
```

| profile | 说明 |
|---|---|
| `desktop` | 桌面端一般自带，界面里能用 `/agent-teams` |
| `headless` | **MCP 走这个**，默认没有插件 → 章节并行会静默退化成顺序 |
| `web` | 浏览器 UI profile，可选 |

装：`python skills/reelforge/scripts/dsh_teams.py --install headless`（装完重启 Harness 进程）。

两个硬约束：

1. headless **没有 UI**，建团队必须 `approval="automatic"`，否则卡在审批面板
2. headless 沙箱是 **workspace-write**，只允许写**会话工作区（= 任务 cwd）**，
   所以任务必须在项目目录下启动，否则写工程文件被拒

### 4.6 DeepSeek Harness 开团队

```bash
# 桌面端：Plugins → Add plugin → github:NanmiCoder/dsh-agent-teams
# 或 CLI：
dsh plugin --profile web add --save-exact @nanmicoder/dsh-agent-teams@0.1.27
```

装完重启 Harness。执行 skill 的任务包会以 `/agent-teams ` 开头，
第 2..N 章并行；没装就退化为顺序，不影响出片。

### 4.7 配置

| 文件 | 改什么 |
|---|---|
| `skills/reelforge/config/pipeline.yaml` | 角色、模型、参考度、画幅 |
| `skills/reelforge/config/personas.yaml` | 账号人设、参考音频路径 |
| `skills/reelforge/config/tts.yaml` | IndexTTS 服务地址与启动命令 |

`install.sh` 会从 `*.example.yaml` 生成初始配置，按注释改即可。

## 4.7 两种模式怎么选

| 模式 | 装法 | 谁当总控 | 怎么触发 |
|---|---|---|---|
| solo | `bash install.sh --dsh`（任意一个） | 同一个 agent | 依次做总控/写稿/执行，最省事 |
| trio | `bash install.sh --workbuddy --antigravity --dsh` | WorkBuddy | 在 WorkBuddy 里说「做一条 X 片子」 |
| duo | `bash install.sh --antigravity --dsh`（或 `--codex`） | **你** | 在 Harness / Codex 里说「按 reelforge-duo 做一条 X 片子」 |

duo 模式的执行者（也就是总控）会：

1. `duo.py handoff` 生成交接稿 → 你整段粘给 Antigravity
2. 它收稿后跑参考度审计 → 退回重写或请你拍板
3. 之后的工程、音频、录屏它自己干，每道门停下来问你

Codex 用户：`~/.codex/skills/` 已装好四份 skill；
另外 `~/.codex/AGENTS.md` 里加一行「视频任务先读 reelforge-duo 的 SKILL.md」即可。

DSH 用户同理：`~/.dsh/skills/` 装 `reelforge` / `reelforge-duo` / `reelforge-runner`，
`~/.dsh/AGENTS.md` 里指向 `reelforge-duo`。duo 的 `duo.py` 会自己在
`.workbuddy` / `.dsh` / `.codex` / `.claude` / `.gemini` 里找总控脚本，
也可以用 `REELFORGE_HOME` 指定。

## 5. 换一套 agent

| 角色 | 可替换为 | skill 放哪 |
|---|---|---|
| 总控 | Claude Code / Codex CLI / Cursor（对话式） | `~/.claude/skills`、`~/.codex/skills`，或项目 `AGENTS.md` 里引用 |
| 写稿 | Claude / GPT / Gemini（任意有文件读写能力的会话） | 支持 skills 的放 skills 目录；不支持的把 `skills/reelforge-writer/SKILL.md` 贴进系统提示 |
| 执行 | Claude Code / Codex CLI / 本地脚本 | 同上；没有 MCP 就用 shell 直接调用 |

**没有 MCP 也能跑**：总控把任务包写成 `tasks/*.md`，你复制给对应 agent；
agent 完成后改 `state.json`。MCP 只是把「复制粘贴」自动化。

## 6. 单 agent 降级模式

只有一个人（一个 agent）时，按顺序自己扮演三个角色：

1. 用 `reelforge-writer` 的规则写稿 → `script_gate`
2. 用 `reelforge-runner` 的流程出片 → `chapter_gate` / `audio_gate`
3. 每步仍然 `state.py gate`，不要跳

效果一样，只是没有并行。

## 7. 验收安装

```bash
python skills/reelforge/scripts/probe.py          # 全 ok
python skills/reelforge/scripts/assets.py init    # 素材库就绪
python skills/reelforge/scripts/state.py init --work /tmp/rf-test
bash skills/reelforge/vendor/web-video-presentation/scripts/scaffold.sh --list-themes
```

四项都过，说明环境可用。

## 8. 常见问题

| 问题 | 原因 | 处理 |
|---|---|---|
| `probe.py` 报 jq 缺失 | 没装 jq | Windows `winget install jqlang.jq`；mac `brew install jq` |
| `scaffold.sh` 卡在 npm install | npm 源慢 | `npm config set registry https://registry.npmmirror.com` |
| MCP 里看不到两个 server | 路径写错 / python 不对 | 用绝对路径；先在终端手动跑 `python server.py` 看报错 |
| Antigravity 会话建不起来 | 桌面端没登录 / 端口变了 | 打开 Antigravity 确认登录；桥接会自己找端口 |
| DSH 任务一直 running | 模型额度或登录态 | 打开 Harness 看队列；`dsh --version` 确认 CLI 可用 |
| 写稿 agent 不读 skill | 它没有 skills 机制 | 把 SKILL.md 内容贴进首条消息（任务包已包含路径和摘要） |
