# 路线 B：EAC film（`__seek(t)` 时间轴）出片

> 路线 A 是「wvp 章节 + 录屏」；路线 B 是「整片一个确定性 HTML，按 t 逐帧渲染」。
> 两条路线的交付物相同：MP4 + SRT + 工程。

## 什么时候选 B

| 条件 | 说明 |
|---|---|
| 片长 30–90s | 再长逐帧渲染成本高，且观众注意力撑不住 |
| 强动效/电影感 | 镜头推拉、逐字字幕、浮窗 UI 演示 |
| 用户已装 EAC 插件 | 能读 `motion-promo-film` 模板与动效库；没装就回 A |
| 不需要逐拍长口播 | 旁白按拍排时间轴即可，不需要浏览器实时录屏 |

## film.html 契约（必须满足）

```js
window.__FPS = 30;
window.__DUR = 63.2;          // 秒
window.__ready = true;        // 字体/素材就绪后
window.__seek = (t) => { ... } // 纯函数：任意 t 渲染一帧，幂等
```

禁止 CSS `transition/animation`、`requestAnimationFrame`、渲染期 `Math.random()`；
所有运动由 `__seek(t)` 直接写样式。

## 输入

- `script.json`：`beats[]`（text / visual）
- `narration.json`（`tts.py` 产物）或 `audio-segments.json` + 逐拍 mp3：给出每拍真实时长
- `assets.json`：素材清单
- 模板：`motion-promo-film`（风格/字体/相机/字幕系统见其 `STYLE.md`）
- 风格层：`assets/eac/style-pack.css`（颗粒/暗角/百叶转场）

## 生成骨架

```bash
python <reelforge-runner>/scripts/film_from_beats.py \
  --work <work> --out <work>/film/film.html \
  --title "片名" --style <work>/film/style.css
```

生成的是**卡片式骨架**：每拍一屏（眉题/主标/描述），按 `__seek` 淡入位移。
要模板级的浮窗 UI 演示，按 `STYLE.md` 把对应 section 换成真实 DOM（窗口/表格/弹窗），
时间轴只改数据、不改渲染模式。

## 渲染

### 有 EAC 插件（推荐）

在 EAC 会话里：

```
eac_template_read templateId=motion-promo-film source=true
eac_job_submit type=render-template params={
  "templateId": "motion-promo-film",
  "htmlPath": "<work>/film/film.html",
  "duration": 63.2, "fps": 30, "audioPath": "<work>/film/audio.wav"
}
```

### 没有插件（离线）

```bash
node <runner>/scripts/render_film.mjs --film <work>/film/film.html --out <work>/film/frames
ffmpeg -framerate 30 -i <work>/film/frames/f_%05d.jpg -i <work>/film/audio.wav \
  -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest <work>/film/final.mp4
```

## 音频与字幕

- 逐拍 mp3 按 `narration.json` 的 start 排成一条 `audio.wav`（`mix_timeline.py` 的 bed 构建逻辑可复用）。
- 字幕：同一条时间轴导出 SRT；需要烧录就 `mix_timeline.py --burn`，或渲染前把字幕层写进 film.html
  （推荐后者：字幕在 `__seek` 里控制，帧级精确）。

## 验收（与 A 相同）

```bash
ffprobe -v error -show_entries format=duration -show_entries stream=width,height,codec_type -of default=nw=1 final.mp4
ffmpeg -ss 12.4 -i final.mp4 -frames:v 1 qc_12.4.png   # 每个分节切点 +0.5s 各一张
```

1920×1080、30fps、有音轨；时长与 `__DUR` 差 <1s；抽帧无文字裁切/元素重叠。

## 许可

- `motion-promo-film` 按其 `SKILL.md`/NOTICE 使用，不复制源码进本仓库；
- 动效来自 video-shotcraft（Apache-2.0）需署名；
- onetake `motion.js` 是 PolyForm Noncommercial，商用需授权，默认不启用。
