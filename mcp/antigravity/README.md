# antigravity MCP（stdio）

把本机 Antigravity 的能力暴露成 MCP 工具：开会话、等结果、列会话、看视频。

## 依赖

- Antigravity 桌面端已安装并登录
- Windows：`%LOCALAPPDATA%\Programs\antigravity\resources\bin\language_server.exe`
- 其他平台：用 `ANTIGRAVITY_LS_EXE` 指到 `language_server` 可执行文件

## 工具

| 工具 | 作用 |
|---|---|
| `health` | 检查进程、端口、CSRF、可用模型档位 |
| `start_session` | 新建会话（异步），返回 conversation_id |
| `get_result` | 等待会话完成并取最终回复 |
| `list_sessions` | 最近会话 |
| `analyze_video` | 让 Antigravity 看一段视频并回答 |

## 配置

```json
{
  "mcpServers": {
    "antigravity": {
      "command": "python",
      "args": ["<abs>/mcp/antigravity/server.py"]
    }
  }
}
```

## 模型

桥接默认暴露 `flash` / `flash_lite` / `pro`。Antigravity 实际还支持
`gemini-4-argon-low|medium|high`，把 `server.py` 里 `model` 的 enum 加上即可
（`start_session` 会把 `--model=<值>` 透传给 CLI）。

## 说明

- `douyin_cdp.py` 是抓抖音素材的辅助脚本（CDP），不参与 MCP 主流程
- 日志：`%TEMP%\antigravity_mcp.log`
