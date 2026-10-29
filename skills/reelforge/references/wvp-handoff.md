# 出片交接：web-video-presentation（wvp）

渲染层是 vendored 的 `vendor/web-video-presentation`（**v1.2.2**，与上游 manifest 一致，MIT）。
流程、关卡、章节写法都以上游 `vendor/web-video-presentation/SKILL.md` 为准，本文只做接线。

**硬约束：16:9 / 1920×1080**。wvp 是固定舞台 + 点击/键盘驱动 step，不做竖屏、不做响应式。

```bash
VF=<skill 目录>   # C:/Users/dichengxiang/.workbuddy/skills/video-factory
W=$VF/vendor/web-video-presentation
```

## 阶段 0 · 环境

Node 18+（本机 22.22）、npm、**jq**、Git Bash。脚手架会自动 `npm install`；
公司网络慢就先 `npm config set registry https://registry.npmmirror.com`（本机已设）。
jq 用来解析 `audio-segments.json`，没有会直接报 `jq is required`。

## 阶段 1 · 内容（wvp Phase 1）

```bash
python scripts/make_wvp_inputs.py --work work/<slug>
```

产出三份，落在 `work/<slug>/`：

| 文件 | 作用 |
|---|---|
| `script.md` | 口播稿，按 `---` 切节拍（每拍一段，不改写） |
| `outline.md` | 开发计划：1 章 / N step，每 step 一行屏幕内容 + 信息池 |
| `article.md` | 画面细节源（有 `evidence.md` 就直接用它） |

短视频映射：**1 章 = 整条片子，N step = script.json 的 N 拍**。
要拆多章（>60 秒）就手改 `outline.md`，再让 chapter agent 按章实现。

## 阶段 2 · Checkpoint Plan（🛑 关卡）

一次对齐 5 件事，缺一不可：

1. 稿子（`script.md`）改不改
2. 开发计划（`outline.md`）的章节 / step / 估时
3. 主题：先 `bash $W/scripts/scaffold.sh --list-themes`，按 `theme.json` 的 `bestFor` 推 2–3 个
4. 素材：封面/截图/字体从哪来（没有就 placeholder，并写进 outline 素材清单）
5. 开发模式：A 逐章（默认）/ B 顺序 / C 并行 subagent

## 阶段 3 · 建工程（wvp Phase 2.1–2.3）

```bash
bash $W/scripts/scaffold.sh work/<slug>/presentation --theme=<id>
cp assets/tts-providers/indextts.sh work/<slug>/presentation/scripts/tts-providers/
```

第 1 章必须主线程做完、**🛑 用户验收**；第 2..N 章按选定模式。
每章按 `$W/references/CHAPTER-CRAFT.md` 写，硬规则：

- 固定 1920×1080 舞台，`transform: scale` 适配，不写响应式
- 每步独占整屏（`if (step === N) return <FullScene />`），无定时器
- `narrations.ts` 是 step 数和口播文本的**唯一真相源**，改 step 必须同步它
- 内容驱动动画：先找画面里的内在动作，找不到才用入场动画兜底
- 逐步揭示：列表 1 项 = 1 step，禁止一次全展示
- 反 AI 俗套：紫粉渐变、圆角彩色边框、假插画、emoji 一律不用

## 阶段 4 · 配音（wvp Phase 3）

```bash
cd work/<slug>/presentation
npm run extract-narrations          # → audio-segments.json
# 🛑 让用户扫一眼文本，确认没有错句/漏句

PRESENTATION_TTS=indextts TTS_PERSONA=ace npm run synthesize-audio
```

- 每步一个 `public/audio/<chapter>/<step>.mp3`，由我们的 IndexTTS 合成
- provider 在 `assets/tts-providers/indextts.sh`，内部调 `scripts/tts_once.py`
- 服务没起会自动拉起（约 40 秒加载），参考音频取 `personas.yaml`
- 换人设：`TTS_PERSONA=gatekeeper`；换参考音频：`TTS_REF_AUDIO=/abs/x.wav`
- 增量合成：已存在的 mp3 会跳过；要重来加 `-- --force`

## 阶段 5 · 录屏（wvp Phase 4）

```bash
npm run dev     # 看终端实际端口
```

- **有音频**：浏览器开 `http://localhost:<port>/?auto=1`，按 SPACE 自动播完 → 录屏 → 裁头尾
- **无音频**：手动逐 step 点击录，后期配音
- 录屏建议 1920×1080、30fps、关掉浏览器 UI（全屏）

## 阶段 6 · 验收

```bash
ffprobe -v error -show_entries stream=width,height,codec_type \
        -show_entries format=duration -of default=nw=1 work/<slug>/presentation/out/final.mp4
```

必须：1920×1080、有 `codec_type=audio`、时长与 outline 估算差 <10%。
不放心的再抽 3 帧看：`ffmpeg -ss 1 -i final.mp4 -frames:v 1 qa/01.png`。

## 检查表

- [ ] 稿子/outline/主题/素材/模式 5 件事都确认过
- [ ] 第 1 章经过用户验收才开始后面章节
- [ ] `narrations.ts` 与 `audio-segments.json`、`public/audio/` 三者数量一致
- [ ] 成片 1920×1080、有音轨、时长对得上
- [ ] 字体已放进项目并 `@font-face`（不能依赖系统字体）

## 常见坑

| 坑 | 处理 |
|---|---|
| `npm install` 卡住 | 换 npmmirror 源；或 `npm install --registry=...` 手动装 |
| `create-vite` 下载失败 | 网络问题，重跑 scaffold；已有目录先删掉 |
| `npm run dev` 端口变了 | 以终端打印为准，`?auto=1` 跟在真实端口后面 |
| 音频和 step 对不上 | 改了 `narrations.ts` 没重跑 extract / synthesize；删 `public/audio/<id>/` 重合成 |
| 中文变方块 | 主题字体没自托管；把字体放 `public/fonts/` 并改 tokens |
| 录屏有浏览器边框 | 用全屏 + 隐藏光标；或 OBS 窗口捕获裁剪 |
