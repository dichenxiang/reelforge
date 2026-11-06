# 路线 C：离线逐帧（Pillow + FFmpeg rawvideo）出片

> **定义**：不启浏览器、不装 EAC，用 Python 纯函数画出每一帧，通过 `rawvideo` 管道喂给 FFmpeg 编码，再拼段、混音、整片重编码。
> 这是 `muse-skill-prompt-介绍片.mp4`（77.367s / 1920×1080 / 30fps / H.264+AAC）**实际使用的路线**，此前文档只写了 A/B，与实际执行脱节，故正式登记。

## 0 · 四条路线先选一条，别混着说

| 路线 | 做法 | 适合 | 前提 |
|---|---|---|---|
| **A**（默认） | wvp 网页章节 + `record_auto.mjs` / OBS 录屏 | 口播驱动、50 拍以上、要真实网页交互 | wvp vendor + 浏览器 |
| **B** | 整片一个确定性 `film.html`，`__seek(t)` 逐帧渲染 | 30–90s 强动效、电影感 | EAC design world 插件 |
| **C** | **Pillow 逐帧 → rawvideo → FFmpeg 编码 → concat → 混音** | 逐帧确定性、字幕/音效与口播严格对齐、录屏/截图/视频片段混排、无浏览器/EAC | Python + Pillow + FFmpeg |
| **D** | wvp 主体 + EAC 风格层 + 1–2 个库动效（A 的增强，原 eac-bridge 里叫 C） | 已有 wvp 工程、想立刻提质感 | A 的工程 + EAC 模板 |

> 旧版 `eac-bridge.md` 把「混合」叫 C；统一编号后改为 **D**，避免与离线逐帧冲突。选完必须写进 `state`（`--meta render=A/B/C/D`），**不许把 C 说成 A 或 B**。

## 1 · 什么时候选 C

**选 C**：
- 字幕、气泡、音效要卡到**句子级**时间码，误差 <0.1s；
- 素材是本地录屏 / 截图 / 视频片段，需要精确 `-ss` 取段、原速播放、叠加放大框；
- 没有浏览器录屏环境或没装 EAC；
- 要求「改一处 → 只重渲受影响段 → 可复现」；
- 片长 30–120s，逐帧成本可接受。

**别选 C**：
- 需要真实网页交互、滚动、CSS/3D 动效 → 回 A；
- 要模板级电影感且已装 EAC → 回 B；
- 超长片 / 大量章节要并行 → 逐帧渲染慢，回 A。

## 2 · 工程结构（照本片实际目录）

```
<project>/
  make.py          # 镜头表 SEGS + 句子级时间码 + 分段调度（唯一编排入口）
  vid.py           # 纯函数帧渲染：render_frame / render_anim / render_live / render_frame_zoom
  sfx.py           # 读 timeline.json 的 marks/beats/sents 生成音效轨
  finalize.py      # picture + narration + sfx → 整片重编码 + 混流
  tts/             # 逐句 TTS 产物（一句一个文件，再拼 narration.wav）
  _build/
    timeline.json  # ★ 唯一时间真相源：每句 (text, start, dur)、marks、beats
    narration.wav
    sub_v8/        # 字幕 PNG（目录名带版本，换稿必须换指纹）
    seg/           # 每个镜头的 mp4 片段
    sfx.wav
    picture.mp4    # 无声画面
    still_*.jpg    # 素材静帧（缓存键含源文件与 ss）
```

**时间真相源只有一份**。逐句 TTS 得到 `sents = [(text, start, dur)]`，字幕 PNG 的 `enable='between(t,st,en)'`、气泡 `marks/beats`、音效 cue 全部从 `timeline.json` 推导。禁止按字数估时，禁止各自按比例推算。

## 3 · 命令序列

```bash
cd <project>
python make.py        # 逐段渲染 → _build/seg/*.mp4 → -f concat → picture.mp4
python sfx.py         # → _build/sfx.wav
python finalize.py    # picture + narration + sfx → 成片（libx264 + AAC + faststart）

ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of default=nw=1 <成片.mp4>
python "$RF/scripts/fx_pipeline.py" check    # 效果库全量回归，必须 0 异常
```

`finalize.py` 关键参数（**整片统一重编码，不要 `-c:v copy` 拼不同参数的段**）：

```
-profile:v high -level 4.0 -g 60 -keyint_min 60 -sc_threshold 0
-bf 2 -refs 3 -r 30 -movflags +faststart
```

## 4 · 帧与片段渲染要点

- **帧 → 视频**：`-f rawvideo -pix_fmt rgb24 -s 1920x1080 -r 30 -i -`，Python 把 `img.tobytes()` 写进 ffmpeg stdin；纯函数 `render_frame(t, total, params) -> PIL.Image`。
- **素材从指定时刻原速播放**：`-ss <源文件起点> -t <成片该露出的时长 + 余量>`，**完整输入**，靠 `setpts=PTS+appear/TB` 做出场偏移、`overlay=...:enable='gte(t,appear)':eof_action=pass` 控显隐。不要 `setpts` 变速、不要定格、不要把输入裁到只够一瞬间。
- **后几块素材消失**的根因通常是某路输入被裁短，`shortest` 截断了链路 —— 输入给足整段。
- **缓存失效**：中间产物按输入指纹命名（`sub_v8`、`still_{src}_{ss:.2f}.jpg`）；旁白时长校验 `abs(dur(narration) - expect) > 0.08` 就删掉重合成；改了文案/配色必须换输出目录。
- **ffmpeg 找不到**：agent 会话 PATH 常缺 ffmpeg；用 `effects/runtime.py` 的 `ffmpeg_bin()`，或设 `REELFORGE_FFMPEG`。在 `import vid` **之前**补 PATH（vid 会冻结当时的环境变量）。

## 5 · 效果库怎么接（C 与 A/B 共用）

两条都行，别再手写动效：

1. **镜头表直调**：`make.py` 里写 `("fx", {"fx": "bar_grow", "params": {...}}, dur)`，由 `import runtime as fx_runtime` 的 `render_frame` / `render_clip` 出片段。
2. **稿子自动配**：`fx_pipeline.py plan --script script.md --out shots.json --with-transitions` → `render --shots shots.json --out-dir clips` → `emit` 生成可粘进 `make.py` 的镜头表。

新动效照旧必须 `register` + `baseline` + 写 `auto` 配方卡，详见 `reelforge/references/effects-library.md`。

## 6 · 验收门（与 A/B 相同的交付物）

- `ffprobe`：1920×1080 / 30fps / H.264 + AAC / 时长与 `timeline.json` 总长差 <0.3s。
- 抽帧逐格看：文字不裁切、转场有前后两幅、后几块素材确实出现、数字与标签不重叠。
- 音画对齐：每句字幕 `start` 与 TTS 实际起点差 <0.1s；音效 cue 不落在句子结束之后。
- `pilot_gate` 先出 15–20 秒样片（最终字体/配色/参数），用户看过再全篇。
- 交付：MP4 + SRT + 工程目录（含 `timeline.json`）。

## 7 · 本路线踩过的坑（硬规则）

| 坑 | 规则 |
|---|---|
| 按字数估时长 → 字幕/气泡/音效漂移 | 逐句 TTS + 单一 `timeline.json` |
| 改了参数画面没变 | 中间产物按"文件存在"缓存了；换指纹或删中间产物 |
| 从素材第 2s 播被做成慢放/定格 | 「从第 2s 开始」指**源文件起点**，按成片该露出的时长**原速**截取 |
| 后两块素材直接消失 | 输入被裁短；恢复完整输入 + `setpts` 偏移 |
| 音画整体错位 | 时间线改过但 `narration.wav` 没重算 |
| 拼接后播放异常 | 整片统一重编码，保证 SPS/PPS、GOP、profile 一致 |
| 效果库换 agent 找不到 | `effects.py where`；索引本地+仓库合并，仓库优先 |

## 8 · 与其它文档的关系

- 路线 A：`wvp-execution.md` / `reelforge/references/wvp-handoff.md`
- 路线 B：`route-b-eac-film.md` / `film_from_beats.py`
- 路线 D（混合）：`eac-bridge.md`
- 五道门与 `pilot_gate`：`reelforge/references/gates.md`（路线 C 同样不跳门）
- 跨 agent 统一路径：`AGENT_ROUTING.md`
