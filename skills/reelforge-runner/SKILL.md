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

### P0.5 出片路线：A（HTML 渲染+录屏）还是 B（EAC film 时间轴）

稿子确认后，**先问用户选路线**，不要默认；选择写进 state：

```bash
python <reelforge>/scripts/state.py set --work "$W" --meta render=A --meta template=<模板id>
```

| 路线 | 做法 | 适合 |
|---|---|---|
| A（默认） | wvp 章节 → `record_auto.mjs` 录屏 → `mix_timeline.py` 混音+字幕 | 口播驱动、50 拍以上、信息密度高 |
| B | 一个确定性 `film.html`（`__seek(t)`）→ EAC `render-template` 逐帧渲染 | 30–90s、强动效、模板级视觉 |

- 有 EAC 插件：`python <runner>/scripts/eac_probe.py --json` 列模板/动效，让用户选模板与风格
- 没插件：回 A，不要假装支持 B
- B 的契约、渲染命令、许可边界：`references/route-b-eac-film.md`
- 生成 B 的骨架：`python <runner>/scripts/film_from_beats.py --work "$W" --out "$W/film/film.html"`

### P0.6 配音方式与预设（必须问）

1. 有 IndexTTS：`python <reelforge>/scripts/tts_once.py --list-presets --out /tmp/x.mp3` 列预设，让用户选
2. 没有 IndexTTS 但有 GPU 条件：提示装 IndexTTS（`D:/indexTTS` 或 tts.yaml 的 start_cmd）
3. 都没有：edge-tts 兜底（`pip install edge-tts`），列 `zh-CN-*` 音色让用户选
4. 用户自带录音/克隆：要 10–20 秒干声，路径写进 personas

合成时把 provider/preset 写进 state：`--meta tts_provider=indextts --meta tts_preset=<预设>`。

### P0.7 字幕（默认要）

- 交付必须带字幕：`mix_timeline.py` 会同时产出 `.srt` 和 `.ass`
- 要烧进画面加 `--burn`（`--font "Microsoft YaHei" --font-size 44 --margin-v 72`）
- 不烧录就交付外挂 `.srt`，并在交付说明写清

### P0.8 录制/混音工具（已下沉）

```bash
node <runner>/scripts/record_auto.mjs --url "http://127.0.0.1:4176/?auto=1" --duration 150 --out out/raw.webm
python <runner>/scripts/mix_timeline.py --raw out/raw.webm --timeline out/raw.timeline.json --segments audio-segments.json --audio-dir public/audio --out out/final.mp4 --burn --srt out/final.srt
```

录屏**用 `vite preview` 的生产构建**（dev server 的旧模块缓存会录到旧章节）。

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

### P3 音频（按用户选择，不默认）

**先问用户用哪种**（写进 state：`--meta tts_provider=... --meta tts_preset=...`）：

1. **IndexTTS 预设**（推荐）：`python <reelforge>/scripts/tts_once.py --list-presets --out /tmp/x.mp3` 列出来让用户选
2. **IndexTTS 参考干声**：10–20 秒干净人声，路径写进 personas 的 `voice.ref_audio`
3. **edge-tts 兜底**：没有 GPU 时用，列 `zh-CN-*` 音色让用户选（需 `pip install edge-tts`）
4. **自定义命令**：`provider=cmd`，接 OpenAI 兼容 / ElevenLabs / 自建服务

**禁止 Windows SAPI**（Huihui / KangKang / Yaoyao）——机械音，宁可不配旁白。

```bash
python <reelforge>/scripts/tts_once.py --text "测试一下旁白" --out /tmp/probe.mp3 --persona <id> --preset "<预设>"
cd "$W/presentation"
npm run extract-narrations
PRESENTATION_TTS=indextts TTS_PERSONA=<id> TTS_PRESET="<预设>" npm run synthesize-audio
```

完成后停下写 gate：

```bash
python <reelforge>/scripts/state.py gate --work "$W" --name audio_gate --artifacts "$W/presentation/public/audio"
```

| 问题 | 处理 |
|---|---|
| 某段时长不合 | 回 outline 调 step 数；不许用 SAPI 顶替，也不许为压时长删内容 |
| 想整体加速/减速 | 改 personas 的 `voice.rate` 重合成，不在视频里变速 |
| 服务起不来 | 按 `config/tts.yaml` 的 start_cmd 手动起，看 `%TEMP%/vf-tts-server.log` |
| 无 GPU | 走 edge-tts，并在汇报里注明「edge 兜底」 |

### P4 录屏（路线 A）

**用生产构建，不用 dev server**（旧模块缓存会录到旧章节）：

```bash
cd "$W/presentation"
npm run build
npx vite preview --port 4176 --host 127.0.0.1
node <runner>/scripts/record_auto.mjs --url "http://127.0.0.1:4176/?auto=1" --duration <片长+15> --out out/raw.webm
```

人工模式：打开 `?auto=1`，点一下开始，OBS 录；保留同步白块或用后续手工对轨。

### P5 混音 + 字幕 + 验收

```bash
python <runner>/scripts/mix_timeline.py --raw out/raw.webm --timeline out/raw.timeline.json --segments audio-segments.json --audio-dir public/audio --out out/final.mp4 --burn --srt out/final.srt
ffprobe -v error -show_entries format=duration -show_entries stream=width,height,codec_type -of default=nw=1 out/final.mp4
ffmpeg -ss 12.4 -i out/final.mp4 -frames:v 1 qc_12.4.png
```

必须 1920×1080、30fps、有音轨、带字幕（烧录或外挂 SRT）；时长与旁白差 <1s。

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
