# ReelForge

**三端协作的短视频生产流水线。** 一个总控 agent 拆任务，一个写作模型写口播稿，一个编码 agent 把稿子做成 16:9 的视频。
出片有两条路线：**A** 网页章节 + 录屏（默认），**B** 确定性 HTML + EAC `__seek(t)` 逐帧渲染（可选）。

不是「一句话生成视频」的黑盒。它把流程拆成可验收的四道门：

```
主题 / 参考片
   │
   ├─ 拆解（可选，参考度默认 40%，上限 60%）
   ├─ 口播稿  ────────────── 🛑 script_gate
   ├─ 选路线/模板/配音/字幕 ─ 🛑 options_gate
   ├─ 网页演示（wvp）  ────── 🛑 chapter_gate
   ├─ 逐 step 配音  ──────── 🛑 audio_gate
   └─ 录屏 + 混音 + 字幕 ───── 🛑 final_gate → MP4 + SRT
```

## 为什么是三个 agent

| 角色 | 能力 | 默认实现 |
|---|---|---|
| 总控 | 读写文件、发任务、等结果、卡验收 | WorkBuddy / Claude Code / Codex |
| 写稿 | 强写作、文件读写 | Antigravity（Gemini 4 Argon Medium） |
| 执行 | shell、node、改代码 | DeepSeek Harness（官方来源，`deepseek-flash`＝V4.1 Flash，思考 max） |

**角色和产品解耦**：换任何一个都能跑，见 [`DEPLOY.md`](DEPLOY.md)。
没有 MCP？总控把任务包写成 markdown，人工转发；agent 改 `state.json` 即可。

## 快速开始

```bash
git clone https://github.com/dichenxiang/reelforge.git
cd reelforge

bash install.sh --workbuddy --antigravity --dsh   # 按你有的 agent 选
bash install.sh --with-wvp                        # 拉 web-video-presentation
bash install.sh --check                           # 依赖体检（python/node/ffmpeg/jq/wvp/TTS）
```

第一次部署先**建人设**（不预设“阿测/学长”，1 个或多个人设都可以）：

```bash
python skills/reelforge/scripts/personas_init.py
```

然后起第一条：

```bash
python skills/reelforge/scripts/state.py init --work work/demo --title "第一条片子"
python skills/reelforge/scripts/pack_task.py writer --work work/demo
# 把 work/demo/tasks/writer.md 交给写稿 agent；它开工前会先问：人设 / 目标 / 受众 / 素材
```

稿子确认后再定四件事（路线 A/B、模板、配音方式/预设、字幕），再生成 runner 任务包：

```bash
python skills/reelforge/scripts/pack_task.py runner --work work/demo --render A --template <id> --tts-provider indextts --tts-preset "<预设>" --subs burn
```

详细流程见 [`skills/reelforge/SKILL.md`](skills/reelforge/SKILL.md)。

## 两种模式，四个 skill

> 写稿规范**不另立**：口播风格、三层自检（形式 / 风骨 / 念出来）、
> `outline.md` 格式，全部直接用上游 `web-video-presentation` 的
> `references/SCRIPT-STYLE.md` 与 `references/OUTLINE-FORMAT.md`；
> 我们只额外加 4 条（16:9、单屏 ≤14 字、人设禁词、参考度 ≤60）。

| 模式 | 总控 | 组成 | 适合 |
|---|---|---|---|
| **trio** | WorkBuddy（agent 当总控） | `reelforge` + `reelforge-writer` + `reelforge-runner` | 批量、无人值守，手机上也能盯 |
| **duo** | **你**（人在电脑前） | `reelforge-duo` + `reelforge-writer` + `reelforge-runner` | 边看边调，一次性高质量 |

两种模式**共用同一套门槛、脚本、素材库和参考度审计**，
差别只在「谁派活、谁问验收」。切换：`config/pipeline.yaml` 的 `mode`。

| skill | 给谁 | 内容 |
|---|---|---|
| [`reelforge`](skills/reelforge/) | trio 总控 | 状态机、参考度审计、任务包、素材库、验收卡 |
| [`reelforge-duo`](skills/reelforge-duo/) | duo 总控（执行 agent 兼） | 交接稿生成、收稿校验、给人生成验收卡 |
| [`reelforge-writer`](skills/reelforge-writer/) | 写稿 | 口播化规则、去 AI 味、参考预算、输出契约 |
| [`reelforge-runner`](skills/reelforge-runner/) | 执行 | wvp 全流程、agent-teams 并行、TTS、录屏、验收 |

## 素材库

wvp 只管单条片子的素材清单，跨片子复用是空白。ReelForge 补了一层：

```bash
python skills/reelforge/scripts/assets.py add cover.png --tags brand --license own
python skills/reelforge/scripts/assets.py search --tag gpu
python skills/reelforge/scripts/assets.py materialize --work work/demo --query gpu
```

sha256 去重、授权字段、`used_in` 追踪，交付时能直接出素材授权清单。
详见 [`skills/reelforge/references/asset-library.md`](skills/reelforge/references/asset-library.md)。

## 仓库结构

```
skills/
  reelforge/          trio 总控 skill（scripts + references + 配置示例）
  reelforge-duo/      duo 总控 skill（人在前）
  reelforge-writer/   写稿 skill
  reelforge-runner/   执行 skill（含 record.mjs）
mcp/
  antigravity/        Antigravity 的 stdio MCP 桥接
  deepseek-harness/   DeepSeek Harness 的 stdio MCP 桥接
install.sh            安装 skill / 拉 wvp
DEPLOY.md             人读的部署说明
AGENT_DEPLOY.md       给 AI 读的自部署指令
```

## 依赖

Python 3.10+ · Node 18+ · jq · ffmpeg · git
可选：本地 IndexTTS（克隆音色）、dsh-agent-teams（章节并行）

## 许可

MIT。内置/依赖的上游项目：
- [web-video-presentation](https://github.com/ConardLi/garden-skills/tree/main/skills/web-video-presentation)（MIT，不随仓库分发，安装时拉取）
- [dsh-agent-teams](https://github.com/NanmiCoder/dsh-agent-teams)（MIT，可选插件）
