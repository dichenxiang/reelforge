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

### P0 开工前自检（先做，别等做到一半才发现）

在动手改代码之前，把这几件事查清楚并报给用户；**任何降级方案都要先说，不要默默换掉**：

```bash
# 1) 旁白能力（决定这条路走不走得通）
python <reelforge>/scripts/tts_once.py --text "测试一下旁白" --out probe.mp3 --persona <ace|gatekeeper>

# 2) 团队能力（MCP 走 headless profile，插件默认没装）
python <reelforge>/scripts/dsh_teams.py --status
# 显示 headless 未开启 → 装上（装完要重启 Harness 进程）：
python <reelforge>/scripts/dsh_teams.py --install headless

# 3) 素材尺寸是否够用（截图/商品图能不能撑满 1920×1080）
python - <<'PY'
from PIL import Image
import glob, sys
for p in glob.glob(r"<素材目录>/**/*.*", recursive=True):
    try:
        w, h = Image.open(p).size
        print(f"{p}  {w}x{h}")
    except Exception:
        pass
PY
```

自检结论要写进汇报：旁白用什么音色（IndexTTS 克隆 / edge 兜底）、素材怎么呈现
（浏览器窗口框 / 手机框 / 画面内放大 ≤1.5×）、**时长不由你压缩**、
**团队是否可用（headless 有没有 agent-teams）**。

### 沙箱规则（会让你白跑一遍的那种坑）

DSH headless 的文件沙箱是 **workspace-write**：只允许写**会话工作区**（= 你启动任务时的
cwd）及其临时目录。所以：

- 任务必须在**项目目录**下启动（`cwd` 指向工程根），否则写 `src/`、`public/` 会被拒
- 需要写别处 → 在任务里说明并让 agent 改用会话工作区内的相对路径
- 遇到 `[sandbox: file access denied under workspace-write mode]`，别重试同一个路径，
  先确认 cwd 是不是项目目录

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

### P3 音频（旁白：必须用 IndexTTS 克隆音色）

**唯一允许的旁白来源是本机 IndexTTS 克隆音色**，对应账号人设：

| 人设 | 参考音频 | 说明 |
|---|---|---|
| ace（阿测） | `D:/indexTTS/voices/ace_ref.wav` | 20 多岁男声，偏快 |
| gatekeeper（把关学长） | `D:/indexTTS/voices/gate_ref.wav` | 沉稳男声，偏慢 |

**禁止使用 Windows SAPI（Huihui / KangKang / Yaoyao 等）或任何系统音色**——
那些是机械音，和账号人设不符。也不要因为「服务没在跑」就退化成系统配音：
IndexTTS 服务没起时**会自动拉起**（约 40 秒加载），等它就行。

先自检（一条命令判断能不能用）：

```bash
python <reelforge>/scripts/tts_once.py --text "测试一下旁白" --out /tmp/probe.mp3 --persona ace
```

能出 mp3 就说明服务、参考音频、ffmpeg 都正常。报「连不上」时看 `%TEMP%\vf-tts-server.log`。

正式合成：

```bash
cd "$W/presentation"
npm run extract-narrations
PRESENTATION_TTS=indextts TTS_PERSONA=<ace|gatekeeper> npm run synthesize-audio
```

| 问题 | 处理 |
|---|---|
| 某段时长不合 | 回 outline 调 step 数，**不许用 SAPI 顶替，也不许为压时长删内容** |
| 想整体加速/减速 | 改 `personas.yaml` 的 `voice.rate`，重合成，不要在视频里做变速 |
| 服务起不来 | 手动双击 `D:/indexTTS/extracted/IndexTTS2.0_v3/start_server.bat`，再试 |
| 真没有 IndexTTS 的机器 | 才用 edge-tts（`--provider edge`），并在汇报里注明「用的是 edge 兜底」 |

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
| `<reelforge>/references/tts.md` | 合成旁白前（IndexTTS 服务、参考音频、故障排查） |
| `<reelforge>/vendor/web-video-presentation/SKILL.md` | Phase 2–4 细节 |
| `<reelforge>/vendor/web-video-presentation/references/CHAPTER-CRAFT.md` | 写每一章前 |
