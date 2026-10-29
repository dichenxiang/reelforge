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

## 模型

- `deepseek-v4.1-flash`（默认，1M 上下文，支持 `low|high|max` 思考强度）
- `deepseek-flash`
- `deepseek-v4-pro`

ReelForge 默认用 `deepseek-v4.1-flash` + `reasoning_effort=max`。

## 注意

- 同一时间可以起多个 job，但同一个工作目录里并行改代码要自己防冲突
- 日志：`%TEMP%\dsh_mcp.log`
- 会话索引：`<tool>/sessions.json`（运行时生成，不随仓库分发）
