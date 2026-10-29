# 三端编排

## 1. 角色契约

| 角色 | 必须做 | 禁止 |
|---|---|---|
| 总控 | 建 state、组任务包、审计、发验收卡、批准后推进 | 自己写稿、自己写章节代码 |
| 写稿 | 产出 script.md / script.json / writer-notes.md，自检并停 | 写代码、开工程、改主题 |
| 执行 | 按 wvp P0–P5 做工程/音频/录屏，每阶段写 state 并停 | 改文案、换画幅、改 wvp 源码 |

三方只通过 `work/<slug>/` 里的文件协作。换实现（Claude Code / Codex / 其他模型）
只要读写同一份文件，流程不变。

## 2. 状态机

```
intake → reference? → script → script_gate → build → chapter_gate
       → audio_gate → record → qa → final_gate → deliver → done
```

`status`：`running` / `awaiting_user` / `blocked` / `approved` / `done`。

常用命令：

```bash
python scripts/state.py init  --work work/x --title "片名"
python scripts/state.py set   --work work/x --stage build --status running --job runner=job_123
python scripts/state.py gate  --work work/x --name chapter_gate --artifacts path/to/ch01
python scripts/state.py approve --work work/x --gate chapter_gate --note "过"
python scripts/state.py show  --work work/x --json
```

## 3. 轮询与同步

MCP 是**拉模型**，agent 不会主动推消息。总控的循环：

1. `start` / `start_session` 拿到 job_id / conversation_id，写进 state.jobs
2. 每隔一段时间 `result(job_id)` / `get_result(conversation_id)` 取最新输出
3. 看到 agent 把 state 写成 `awaiting_user`，就在会话里发验收卡
4. 用户确认 → `state.py approve` → 给 agent 下一阶段任务（`continue_session` 保留上下文）

超时策略：
- 5 分钟没动静 → `state.py show` 看 stage 有没有前进
- 20 分钟没动静 → 问 agent「卡在哪」，仍无进展就 `blocked` 并告知用户
- 不要因为等待就重开 session，会丢上下文

## 4. 验收卡模板（≤10 行）

```
【script_gate】<片名>
拍数 6 · 预估 42s · 参考度 38/60
产物：work/x/script.md · script.json
自检：无禁用词 ✓ 每拍≤14字 ✓ 结构 3 段
⏭ 回「过」进工程；回「改：…」我打回重写
```

```
【chapter_gate】第 1 章
产物：presentation/src/chapters/01-hook
自检：tsc ✓ 3 步 12.4s 与 outline 差 3%
⏭ 回「过」开并行；回「视觉太素」我让 runner 改
```

```
【audio_gate】6 段音频
总时长 41.8s（outline 42s，差 0.5%）
异常：无；第 4 段 5.6s，偏长但可接受
⏭ 回「过」进录屏
```

## 5. MCP 调用速查

**Antigravity（写稿）**

```
start_session(prompt=<tasks/writer.md 内容>, model="pro" 或改桥接后的 argon, title="writer-<slug>")
get_result(conversation_id, timeout=900)
```

**DeepSeek Harness（执行）**

```
start(task=<tasks/runner.md 内容>, cwd=<work 绝对路径>, model="deepseek-v4.1-flash",
      reasoning_effort="max", timeout=1800)
result(job_id, timeout=900)
continue_session(session_id, task="用户确认第 1 章，继续第 2..N 章")
```

并行章节用 `/agent-teams` 前缀（见 `reelforge-runner/references/wvp-execution.md`）。

## 6. 失败处理

| 情况 | 动作 |
|---|---|
| 写稿超参考度 | 打回，附 similarity 的 hint；两次不过就降预算到 30 |
| 执行卡在 scaffold | 检查 npm 源（npmmirror）、node 版本 |
| 执行卡在章节 | 看是否缺 `CHAPTER-CRAFT.md` 上下文；补任务包再继续 |
| 音频数量对不上 | 让 runner 重跑 extract；不要手动补文件名 |
| 录屏失败 | 切人工模式，不要为了赶时间降低验收标准 |
