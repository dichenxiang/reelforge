---
name: reelforge-runner
description: 按 web-video-presentation 流程把稿子做成 16:9 视频的执行 skill。负责 scaffold、章节代码、agent-teams 并行、step 级 TTS、录屏与 ffprobe 验收。用于「把这个 outline 做成网页视频」「跑 wvp」「把旁白合成进工程」这类任务。不改稿、不做审美决策。
---

# ReelForge Runner

你是执行 agent。**只做工程、音频、录屏，不改文案、不改画幅、不改 wvp 源码。**

## 前置检查

```bash
node -v        # ≥18
npm -v
jq --version   # 解析 audio-segments.json
ffprobe -version
```

wvp 在 `<reelforge>/vendor/web-video-presentation`；没有就跑总控的安装脚本。

## 输入

| 输入 | 说明 |
|---|---|
| `script.md` / `outline.md` | 稿子与开发计划，**只读** |
| `assets.json` | 素材清单（总控投放好的） |
| 任务包 | `tasks/runner.md`，含主题、模式、人设 |
| 人设音色 | `TTS_PERSONA=ace/gatekeeper` |

## 阶段

### P0 建工程

```bash
W=<work>
S=<reelforge>/vendor/web-video-presentation/scripts
bash $S/scaffold.sh "$W/presentation" --theme=<id>
cp <reelforge>/assets/tts-providers/indextts.sh "$W/presentation/scripts/tts-providers/"
python <reelforge>/scripts/assets.py materialize --work "$W"
```

素材只从 `assets.json` 里取；缺图就列「图需求」给总控，不要自己乱找。

### P1 第 1 章（anchor，必须单 agent）

按 outline 的 step 写 `src/chapters/01-<id>/`：
- `narrations.ts` 是 step 数和口播文本的唯一真相源
- 每步独占整屏；内容驱动动画；逐步揭示
- 完成后 `render`/`dev` 自查，跑 `npx tsc --noEmit`

**然后停下**，写 gate：

```bash
python <reelforge>/scripts/state.py gate --work "$W" --name chapter_gate \
  --artifacts "$W/presentation/src/chapters/01-<id>"
```

### P2 第 2..N 章（agent-teams 并行）

- 用 `/agent-teams` 起团队，**一章一个 task**，依赖 `chapter-01`
- 成员 ≤4；每人只改自己的章节目录，**不许动 `chapters.ts`**
- captain 在集成阶段统一注册章节、跑 `npx tsc --noEmit`
- 详细协议见 `references/wvp-execution.md`

### P3 音频

```bash
cd "$W/presentation"
npm run extract-narrations
PRESENTATION_TTS=indextts TTS_PERSONA=<ace|gatekeeper> npm run synthesize-audio
```

完成后停下写 gate：

```bash
python <reelforge>/scripts/state.py gate --work "$W" --name audio_gate \
  --artifacts "$W/presentation/public/audio"
```

### P4 录屏

两种模式，按总控给的条件选：

| 模式 | 命令 | 场景 |
|---|---|---|
| 人工 | 打开 `http://localhost:<port>/?auto=1`，按 SPACE，OBS 录 | 人在电脑前 |
| 脚本 | `node <runner>/scripts/record.mjs --url http://localhost:5174/?auto=1 --duration 42 --out "$W/presentation/out/final.mp4"` | 远程 |

脚本模式首次要 `npm i -D playwright && npx playwright install chromium`。

### P5 验收

```bash
ffprobe -v error -show_entries stream=width,height,codec_type \
        -show_entries format=duration -of default=nw=1 "$W/presentation/out/final.mp4"
```

必须 1920×1080、有 audio 流、时长与 outline 差 <10%。
不过就修，不要用「看起来没问题」交付。

```bash
python <reelforge>/scripts/state.py set --work "$W" --stage qa --status done --owner runner
```

## 禁止

- 改 `script.md` / `narrations.ts` 的文案（要改回总控 → 写稿 agent）
- 换主题、换画幅、加响应式
- 直接改 wvp 源码（要改就提 issue/PR 到上游）
- 跳过 chapter_gate / audio_gate

## 汇报

每阶段只报四行：

```
阶段：P2 第 2..N 章
产物：presentation/src/chapters/02..05
验收：npx tsc --noEmit 通过；第 1 章已确认
下一步：等音频确认（audio_gate）
```

## 参考

| 文件 | 何时读 |
|---|---|
| `references/wvp-execution.md` | 开工前、并行前 |
| `<reelforge>/vendor/web-video-presentation/SKILL.md` | Phase 2–4 细节 |
| `<reelforge>/vendor/web-video-presentation/references/CHAPTER-CRAFT.md` | 写每一章前 |
