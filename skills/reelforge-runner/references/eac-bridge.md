# EAC 剪辑插件 / 动效库融合

> 适用：本机装了 EAC design world（`eac-design-world`）插件，想用它的**模板风格**与
> **动效库**，但旁白仍然逐拍对齐、不想放弃 wvp 的逐 step 同步。

## 0. 先探测（不依赖 MCP，读安装目录即可）

```bash
python <reelforge>/skills/reelforge-runner/scripts/eac_probe.py --json > <work>/out/eac-pack.json
python <reelforge>/skills/reelforge-runner/scripts/eac_probe.py --motion 转场 --json
```

输出：`installed` / `eacRoot` / `templates[]`（id、path、renderable）/ `motions[]`（150 条：
id、category、energy、duration、recipe、recommended、license）。

`installed=false` → 安静回退纯 wvp，不要报错，也不要编造“已接入”。

## 1. 三条出片路线（先选路线，再动手）

| 路线 | 用什么 | 适合 | 代价 |
|---|---|---|---|
| **A. wvp 逐拍**（默认） | wvp 章节 + 逐拍 IndexTTS + 整页录屏 | 口播驱动、信息密度高、50 拍以上 | 动效受 CSS 限制 |
| **B. EAC film** | `motion-promo-film/templates/film-template.html` + `__seek(t)` 逐帧渲染 | 30–90s 强动效单片、电影感 | 要重写时间轴；节拍与旁白要预排 |
| **C. 混合**（推荐先试） | wvp 主体 + EAC 风格层 + 1–2 个库动效 | 已有 wvp 工程、想立刻提升质感 | 改动小，不破坏逐拍同步 |

路线 B 的命令（EAC 会话内）：

```
eac_library_list kind=template
eac_template_read templateId=motion-promo-film source=true
eac_job_submit type=render-template params={ htmlPath, audioPath, duration, fps:30, templateId:"motion-promo-film" }
```

## 2. 风格层（路线 C 的最小落地）

取 `vendor/motion-promo-film/STYLE.md` 的两件事，不要整套照搬：

1. **颗粒 + 暗角 + 字幕 blur-in**：`4%` 噪点、`radial` 暗角 `0.22`、字幕 `opacity/y/blur` 同一条 outExpo。
2. **深色科技主题变量**（STYLE.md §1.2）只取语义槽位，品牌色沿用账号色，不要换成模板蓝。

落地为独立 CSS 层（`src/styles/eac-layer.css`），在 `App` 里挂两个 `pointer-events:none` 的覆盖层：

```css
.eac-grain { position:fixed; inset:0; z-index:80; pointer-events:none; opacity:.05;
  background-image:url("data:image/svg+xml,...feTurbulence..."); background-size:180px 180px; }
.eac-vignette { position:fixed; inset:0; z-index:79; pointer-events:none;
  background:radial-gradient(ellipse at 50% 45%, transparent 52%, rgba(0,0,0,.26) 100%); }
```

验收：抽 3 帧看暗部是否死黑、颗粒是否过噪；颗粒 opacity >0.07 会糊字幕。

## 3. 动效库（video-shotcraft，150 条）

**能拿什么**：每条有 `category`（转场 / 文字与字卡 / 界面登场 / 节奏与蒙太奇 / 数据与指标…）、
`energy`、`duration`，以及 `gallery/source/<recipe>.md` 里的**参数表**（切点帧号、缓动、
错峰、已知坑）。参考实现是 Remotion TSX，**不能直接扔进 wvp**，要取运动规律用 CSS 复刻。

**选型顺序**：先按语义（翻页 / 强调 / 数据）→ 再按能量（中 / 高）→ 再看时长能否塞进当前拍。

**硬约束**（库自己写的，别违反）：

- 几何擦除类（blinds / wipe）全片 ≤ 2 次，别连用；
- 白闪硬切（paparazzi）全片 ≤ 1 次，且之后要留足 hold；
- 切点钉在旁白停顿上，不钉绝对秒；
- 3D 叶片 / 大位移在 25fps 录屏里会抖，优先用不透明度 / 位移 ≤40px 的动效。

**许可**：video-shotcraft 为 Apache-2.0，成片需在简介/片尾署名；`motion-promo-film-v2`
引用的 onetake 动效库是 PolyForm Noncommercial，商用需授权。

## 4. 融合检查单

- [ ] `eac_probe.py --json` 已生成，路线写进汇报（A / B / C）
- [ ] 风格层变量来自主题，不是硬编码色值
- [ ] 库动效 ≤2 个，且写清来源 recipe id
- [ ] `npx tsc --noEmit` / `npm run build` 通过
- [ ] 成片仍过 ffprobe（1920×1080、30fps、有音轨）与抽帧验收
- [ ] 署名与许可写进交付说明
