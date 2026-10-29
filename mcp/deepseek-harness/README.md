# deepseek-harness MCP（stdio）

把本机 DeepSeek Harness（dsh）的 headless agent 暴露成 MCP 工具：
它会在指定 `cwd` 里真实读写文件、执行命令。

## 依赖

- DeepSeek Harness 桌面端已安装并登录（复用桌面端额度，不需要 API Key）
- 能找到 `dsh` 的 `cli.js`（桥接会自动探测；也可用 `DSH_CLI` 指定）
- Python 3.10+

## 工具

| 工具 | 作用 |
|---|---|
| `health` | 检查安装、凭据、可用模型 |
| `start` | 异步起一个任务，立刻返回 job_id（可并行） |
| `result` | 等任务完成并取结果 |
| `run` | 同步跑一个任务 |
| `continue_session` | 在已有会话上追加一轮（保留上下文） |
| `sessions` | 最近会话 |

## 配置

```json
{
  "mcpServers": {
    "deepseek-harness": {
      "command": "python",
      "args": ["<abs>/mcp/deepseek-harness/server.py"]
    }
  }
}
```

## 模型来源（provider）

| provider | 来源 | 模型 id（部分） |
|---|---|---|
| `deepseek-account` | 官方账号（默认） | `deepseek-flash`（即 V4.1 Flash）、`deepseek-v4-pro` |
| `workbuddy` | WorkBuddy 国内版 | `deepseek-v4.1-flash`、`deepseek-v4-pro`、`glm-5.3`、`kimi-k3.1-pro`、`hy3`… |
| `workbuddy-global` | WorkBuddy 国际版 | `fast-model`、`balanced-model`、`primary-model`、`hy4-preview`… |

调用时传 `provider`；不传就是官方。工具 schema 里的 `model` 是三家并集，
传错来源会明确报错（不会静默降级）。

官方 API 只认 `deepseek-flash` / `deepseek-v4-pro`；`deepseek-v4.1-flash`
是 WorkBuddy 来源的 id，别混用。

思考强度：`low | medium | high | max`，V4.1 系列支持 `max`。

ReelForge 默认：`provider=deepseek-account` + `model=deepseek-flash` + `reasoning_effort=max`。

WorkBuddy 来源要求 headless profile 也装了插件：

```bash
dsh plugin --profile headless add dsh-connect-workbuddy
```

## AgentTeams（并行开发）

- 桌面 profile 一般自带 `@nanmicoder/dsh-agent-teams`；**headless profile 默认没有**
  → MCP 跑的任务其实没有团队能力，`/agent-teams` 会退化成普通对话
- 装到 headless：`python skills/reelforge/scripts/dsh_teams.py --install headless`（装完重启 Harness 进程）
- headless **没有 UI**，建团队必须传 `approval="automatic"`，否则卡在审批面板

## 沙箱与工作区

headless 的文件沙箱是 workspace-write：**只允许写会话工作区（= 任务 cwd）**。
所以 MCP 的 `session_workspace` 默认是 `auto`：

| 项目位置 | 会话工作区 | 效果 |
|---|---|---|
| 在 DSH 默认工作区内 | 默认工作区 | 桌面 App 里能实时看到会话，且可写 |
| 在别处（如 `D://视频//work//x`） | 项目目录本身 | 可写工程；会话按该目录分组，界面里可能要在「工作区」里切换 |

传 `session_workspace="default"` 强制用默认工作区（此时写项目目录会被沙箱拒）；
传 `"cwd"` 强制用给定目录。

## 会话在桌面 UI 里可见

DSH 把会话按 **cwd 分组**存在 `~/.dsh/sessions/<编码路径>/`。MCP 默认用
`session_workspace="default"`，即在桌面端的**「默认工作区」**
（`~/Documents/deepseek-harness/default-workspace`）里开会话，
所以你在 DSH 界面的「工作区 → 默认工作区」里能直接看到这条会话的实时过程。

项目目录不会因此丢：桥接会把真实项目目录写进任务第一行，并要求 agent 先 cd 过去。

传 `session_workspace="cwd"` 则直接在给定目录跑——快一点，但界面里看不到。

## 注意

- 同一时间可以起多个 job，但同一个工作目录里并行改代码要自己防冲突
- 日志：`%TEMP%\dsh_mcp.log`
- 会话索引：`<tool>/sessions.json`（运行时生成，不随仓库分发）
