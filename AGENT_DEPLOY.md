# AGENT_DEPLOY.md — 给 AI 的自部署指令

> 你是被要求部署 **ReelForge** 的 agent。按本文件顺序执行。
> 用户已经提供的信息不要重复问；缺什么就按「缺省规则」处理并记录。
> 所有命令用绝对路径，Windows 用 Git Bash。

## 0. 目标

在用户机器上装好 ReelForge 的三个 skill，并让用户知道怎么开始第一条片子。

ReelForge = 三个角色：

| 角色 | 能力 | skill |
|---|---|---|
| 总控 | 读写文件、调度其他 agent、验收 | `reelforge` |
| 写稿 | 强写作、文件读写 | `reelforge-writer` |
| 执行 | shell、node、python、改代码 | `reelforge-runner` |

先读同目录 `DEPLOY.md` 的背景，再回来执行。

## 1. 探测环境（只读）

```bash
uname -s 2>/dev/null || ver
python --version
node -v
npm -v
jq --version
ffmpeg -version | head -1
git --version
```

记录结果。缺 `jq` / `ffmpeg` 时先装（Windows: `winget install jqlang.jq Gyan.FFmpeg`；
macOS: `brew install jq ffmpeg`；Linux: `apt install jq ffmpeg`）。
**没有 sudo 权限就停下来告诉用户，不要改系统源。**

## 2. 判断角色（问一次就够）

如果用户没说，按这个优先级推断：

1. 当前 agent 是 WorkBuddy / 有会话编排能力 → 总控
2. 当前 agent 只能写文字、不能跑命令 → 写稿
3. 当前 agent 能执行 shell、改文件 → 执行

一个 agent 可以兼任多个角色（单机降级模式），但 skill 要各自装。

## 3. 装 skill

从仓库根目录执行（`REPO` = 本文件所在目录）：

```bash
REPO="$(cd "$(dirname "$0")" && pwd)"
```

按角色复制，**目标目录不存在就创建；已存在同名目录先备份为 `<name>.bak-<日期>`**：

| 角色 | 目标 |
|---|---|
| 总控 | `~/.workbuddy/skills/reelforge` 或 `~/.claude/skills/reelforge` 或 `~/.codex/skills/reelforge` |
| 写稿 | `~/.gemini/antigravity/skills/reelforge-writer`（Antigravity）<br>`~/.claude/skills/reelforge-writer`（Claude）<br>`~/.codex/skills/reelforge-writer`（Codex） |
| 执行 | `~/.dsh/skills/reelforge-runner`（DSH）<br>`~/.claude/skills/reelforge-runner`（Claude Code）<br>`~/.codex/skills/reelforge-runner`（Codex） |

命令示例：

```bash
mkdir -p ~/.workbuddy/skills ~/.gemini/antigravity/skills ~/.dsh/skills
cp -R "$REPO/skills/reelforge"        ~/.workbuddy/skills/
cp -R "$REPO/skills/reelforge-writer" ~/.gemini/antigravity/skills/
cp -R "$REPO/skills/reelforge-runner" ~/.dsh/skills/
```

如果 agent 没有 skills 机制（例如旧版 Cursor），不要硬装：
把 `skills/<role>/SKILL.md` 追加到项目 `AGENTS.md` 或 `.cursor/rules/reelforge.mdc`。

## 4. 装 wvp（执行角色必需）

```bash
cd "$REPO"
bash install.sh --with-wvp
# 等价于稀疏克隆 ConardLi/garden-skills 的 skills/web-video-presentation 到
# skills/reelforge/vendor/web-video-presentation
```

失败就用 zip：

```bash
curl -L -o /tmp/garden.zip https://codeload.github.com/ConardLi/garden-skills/zip/refs/heads/main
unzip -q /tmp/garden.zip -d /tmp/garden
cp -R /tmp/garden/garden-skills-main/skills/web-video-presentation \
      "$REPO/skills/reelforge/vendor/"
```

## 5. 生成配置

```bash
cd "$REPO/skills/reelforge/config"
[ -f personas.yaml ] || cp personas.example.yaml personas.yaml
[ -f tts.yaml ]      || cp tts.example.yaml tts.yaml
```

需要用户提供两样东西，**只问一次**：

1. 参考音频（10–20 秒干声）路径 → 写进 `personas.yaml` 的 `voice.ref_audio`
2. 是否有本地 IndexTTS（有就给服务地址，没有就用 edge-tts）

不提供就保持 example 默认值，并在报告里标「未配置，使用回退方案」。

## 5.1 模型来源（可选）

MCP 默认 `provider=deepseek-account`（官方）、`model=deepseek-flash`（即 V4.1 Flash）、
`reasoning_effort=max`。用户要用 WorkBuddy 额度时：

```bash
dsh plugin --profile headless add dsh-connect-workbuddy
# 调用时传 provider="workbuddy" 或 "workbuddy-global"
```

不要默认切到 WorkBuddy 来源——用户没明确说就用官方。

## 6. 校验（全部要过）

```bash
python "$REPO/skills/reelforge/scripts/probe.py"
python "$REPO/skills/reelforge/scripts/assets.py" init
python "$REPO/skills/reelforge/scripts/state.py" init --work /tmp/reelforge-smoke
bash "$REPO/skills/reelforge/vendor/web-video-presentation/scripts/scaffold.sh" --list-themes
```

期望：

- probe 输出 `{"ok": true, "missing": []}`
- assets 输出 `库已就绪`
- state 输出 `{"ok": true, ...}`
- scaffold 打印主题列表（≥10 个）

任何一项失败：修到过，不要「先这样」。

## 7. 可选：接 MCP

只有当 agent 支持 MCP、且用户希望自动化调度时做：

1. 把 `mcp/antigravity`、`mcp/deepseek-harness` 复制到 `~/.reelforge/mcp/`
2. 在 agent 的 MCP 配置里加两个 stdio server（见 `DEPLOY.md` 4.2）
3. 重启 agent，确认工具列表出现
4. 不支持 MCP → 跳过，用「任务包 + 手动转发」模式

## 8. 写标记文件

在用户工作目录写 `REELFORGE.md`：

```markdown
# ReelForge 已部署
- repo: <REPO>
- 总控 skill: <path>
- 写稿 skill: <path>
- 执行 skill: <path>
- 画幅: 16:9
- 参考度: 默认 40，上限 60
- 开始: python <REPO>/skills/reelforge/scripts/state.py init --work work/<slug>
```

如果项目有 `AGENTS.md` / `CLAUDE.md`，追加 6 行（不要覆盖原文）：

```markdown
## ReelForge
- 视频任务先读 skills/reelforge/SKILL.md
- 写稿用 reelforge-writer，出片用 reelforge-runner
- 口播稿确认后再 scaffold；参考度 ≤60
- 状态文件 work/<slug>/state.json
```

## 9. 汇报模板

```
部署完成：ReelForge
环境：<OS> · python <v> · node <v> · jq <v> · ffmpeg <v>
安装：
  总控  <path>  <ok/失败>
  写稿  <path>  <ok/失败>
  执行  <path>  <ok/失败>
wvp：<版本/路径>  主题数 <n>
校验：probe <ok> · assets <ok> · state <ok> · scaffold <ok>
待用户补：<参考音频 / IndexTTS / 其他>
下一步：<一条可执行的命令>
```

## 10. 禁止

- 不要提交任何密钥、token、账号文件
- 不要覆盖用户已有配置（先备份）
- 不要修改 `vendor/` 里的上游代码
- 不要在没跑通校验前就说「部署完成」
