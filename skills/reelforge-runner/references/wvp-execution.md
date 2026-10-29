# wvp 执行细则

上游 `vendor/web-video-presentation/SKILL.md` 是权威；本文是执行侧的操作清单。

## 1. 工程结构

```
presentation/
  src/chapters/<NN>-<id>/
    <Chapter>.tsx
    <Chapter>.css
    narrations.ts        # step 数 + 文本唯一真相源
  src/registry/chapters.ts
  public/audio/<id>/<N>.mp3
  scripts/{extract-narrations.ts,synthesize-audio.sh,tts-providers/}
```

一条短视频 = **1 章 N 步**，N 就是 `script.json` 的拍数。超过 60 秒再拆多章。

## 2. 一章怎么写

- 固定 1920×1080 舞台，`transform: scale` 适配；不写媒体查询
- 每步独占整屏：`if (step === N) return <FullScene />`
- 画面只由 `step` 决定，不用定时器 / rAF / 随机数
- 列表逐步揭示：1 项 = 1 step
- 文案上屏 ≤14 字；口播文本只进 `narrations.ts`，不整句抄屏
- 反 AI 俗套：紫粉渐变、彩色圆角边框、假插画、emoji 一律不用
- 字体自托管，`public/fonts/` + `@font-face`

## 3. agent-teams 并行

**前提**：DSH 已装 `@nanmicoder/dsh-agent-teams`（0.1.27）。任务消息以 `/agent-teams ` 开头。

推荐任务描述：

```
/agent-teams 在 <work>/presentation 里完成第 2..N 章。
第 1 章已验收，作为风格与代码锚点（读 src/chapters/01-*/）。
每个成员只负责一章：只改自己的 src/chapters/<NN>-<id>/，
不要动 chapters.ts、不要动别人的章节目录。
每章按 references/CHAPTER-CRAFT.md 写，narrations.ts 必须与 outline 的 step 对齐。
完成后自检 npx tsc --noEmit，报告：章节 id、step 数、用的动画手法。
```

规则：

| 项 | 约定 |
|---|---|
| 成员数 | ≤4（再多没有收益，TTS 是串行的） |
| 任务粒度 | 1 章 = 1 task |
| 依赖 | 全部依赖 `chapter-01` |
| 共享文件 | `chapters.ts` 只由 captain 在集成阶段改 |
| 冲突 | 章节目录物理隔离，CSS 前缀按章加（`.ch02-`） |
| 验收 | captain 统一跑 tsc + 逐章截图 |

如果 team 不可用（插件没装/版本不匹配），退化为顺序执行，不要硬起。

## 4. 音频

```bash
npm run extract-narrations          # → audio-segments.json
PRESENTATION_TTS=indextts TTS_PERSONA=ace npm run synthesize-audio
```

- provider 在 `scripts/tts-providers/indextts.sh`，内部调 `scripts/tts_once.py`
- 单段 >6 秒说明该拆 step；<1.2 秒说明信息太薄 → 回总控改 outline
- 重合成：`-- --force` 或删 `public/audio/<id>/`
- 服务没起会自动拉起，日志在 `%TEMP%\vf-tts-server.log`

## 5. 录屏

| 模式 | 做法 |
|---|---|
| 人工 | `npm run dev` → `?auto=1` → SPACE → OBS 录 → 裁头尾 |
| 脚本 | `record.mjs`（Playwright 录制）→ 自动转 mp4 |

`record.mjs` 参数：

```bash
node record.mjs --url "http://localhost:5174/?auto=1" \
  --duration 42 --out out/final.mp4 --size 1920x1080
```

时长 = `audio-segments.json` 里所有音频时长 + 1.5 秒缓冲。

## 6. 常见坑

| 坑 | 处理 |
|---|---|
| npm install 卡住 | `npm config set registry https://registry.npmmirror.com` |
| jq 缺失 | 装 jq 1.8+，否则 synthesize 直接报错 |
| `?auto=1` 不自动播 | 音频数量与 narrations 不一致，重跑 extract |
| 录屏有浏览器边框 | 用脚本模式，或 OBS 窗口捕获裁剪 |
| 中文方块 | 字体没自托管 |
| 端口不是 5173 | Vite 会自动换端口，以终端为准 |
