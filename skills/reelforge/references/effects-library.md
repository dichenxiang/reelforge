# 效果库（跨片子复用动效 · 已接入流水线）

素材库解决「图片视频别重复找」，**效果库解决「动效别重复写、别靠人描述」**。
两者是并列的长期资产：素材在 `~/.reelforge/library/`，效果在 `~/.reelforge/effects/`
并**随 skill 仓库分发一份种子**，换 agent / 换机器都不丢。

## 位置与统一策略

```
~/.reelforge/
  library/     素材：图片 / 视频 / 音频（见 asset-library.md）
  effects/     本地效果库
skills/reelforge/effects/
  index.json   随仓库分发的种子清单（权威源）
  fx/*.py      可运行效果模块
  baselines/   基准帧 jpg（缩略，随仓库分发，换机器也能对照版式）
  runtime.py   渲染运行时
  _core.py     公共纸底/字体/缓动
```

- 默认路径 `~/.reelforge/effects`，环境变量 `REELFORGE_EFFECTS` 可覆盖。
- **索引合并，不是二选一**：`load_index()` 读本地 + 仓库两份，按 `id` 合并，
  **仓库条目优先**。只认本地 → 仓库新增效果本机看不见；只认仓库 → 丢掉本机
  自己 `register` 的效果。
- **模块解析仓库优先**：同一 `id` 在任何 agent 上跑出同一帧；仓库里没有
  同名模块时才回退本地（本机新注册的效果仍可用）。
- 开工时跑 `python scripts/effects.py where` 拿绝对路径并写进 `state.json`
  的 `effects_root`，后续读它，不读环境变量。
- **禁止**把效果只写在项目目录里而不入库。项目里的临时实现，交付前必须登记。

## 配方卡字段（`index.json` 的 item）

```json
{
  "id": "bar_grow",
  "title": "柱条生长",
  "desc": "多根柱条错峰从基线长起，数值跟着柱高走",
  "entry": "fx/data_pack.py:bar_grow",
  "kind": "shot",
  "status": "ready",
  "beats": ["数据", "对比", "列举"],
  "auto": {"title": "{short}", "values": "{numbers?}", "labels": "{labels?}"},
  "requires": [],
  "inputs": ["文", "数据"],
  "params": "values[], labels[], max",
  "energy": "高",
  "intent": "数据,对比,过程演示",
  "pitfalls": ["数值必须随柱高一起涨，别让数字先到"],
  "baseline": "baselines/bar_grow.jpg",
  "used_in": []
}
```

| 字段 | 作用 |
|---|---|
| `entry` | `路径:函数名`，冒号后是函数名**不是路径**；没冒号默认 `render` |
| `status` | `ready` 才可运行；`pending` 是待抽取的老镜头 |
| `kind` | `shot`（整镜）/ `transition`（转场，需前后两帧） |
| `beats` | 适配的语义节拍，`plan` 先按它圈候选，再打分 |
| `auto` | **自动填参数模板**：`{sentence}` 整句、`{short}` 前 12 字、`{value}` 最大数字、`{numbers}` 数字列表、`{labels}` 顿号切词、`{pair}` 拆对句、`{image}/{target}/{focus}` 来自 CLI。抽不到值就跳过该键，用效果自带默认，绝不塞空值 |
| `requires` | 硬依赖（如 `frame_zoom` 要 `image`）。没给素材时 `plan` 不选它 |

## 模块契约（无例外）

```python
def render(t: float, total: float, params: dict | None = None) -> Image.Image:
    """返回 1920×1080 RGB。禁止读外部状态，一切可变项走 params。"""
```

- 纯函数：同样的 `(t, total, params)` 必然得到同一帧；抖动用确定性 `sin`，不用 `random`。
- `t` 是**本镜内相对秒数**，动效在前 0.8–1.4 秒完成，之后保持，方便叠加。
- 转场类额外约定：`total` 一般 0.45–0.8 秒；`a_img` / `b_img` 由 `runtime.prepare()`
  从 `a` / `b`（图片或视频路径）抽帧后传入；没给就用占位帧，保证基准帧永远能跑。
- 需要字体/纸底/调色板用 `effects/_core.py`，不要在模块里另造一套。

## 命令

```bash
# 库管理
python scripts/effects.py where                    # 换 agent 先跑这句
python scripts/effects.py list [--tag 数据]
python scripts/effects.py card bar_grow
python scripts/effects.py path bar_grow
python scripts/effects.py baseline bar_grow --at 1.4 --params '{"values":[20,60,90]}'
python scripts/effects.py check                   # 缺文件 / 缺基准帧
python scripts/effects.py register ./my_fx.py --id my_fx --title "..." --tags a,b

# 稿子 → 镜头表 → 片段（真正接进流水线的那一层）
python scripts/fx_pipeline.py check               # 33 个效果各渲一帧回归
python scripts/fx_pipeline.py plan   --script 稿子.txt --out shots.json \
       [--image 截图.png] [--with-transitions --a a.mp4 --b b.mp4 --trans-every 3]
python scripts/fx_pipeline.py render --shots shots.json --out-dir out/ [--limit 4] [--fps 30]
python scripts/fx_pipeline.py preview --fx bar_grow --at 1.2 --out preview.png
python scripts/fx_pipeline.py emit   --shots shots.json   # 打印可粘进 make.py 的 shots 列表

# 运行时（项目代码直接用这个）
python effects/runtime.py check
python effects/runtime.py clip bar_grow --dur 3 --out out/bar.mp4
```

`runtime.render_frame(fx, t, total, params)` / `runtime.render_clip(fx, dur, out, params, fps)`
是项目侧唯一接缝，内部把帧通过 rawvideo 管道喂给 libx264。

## 自动匹配：不再需要人描述动效

`plan` 的步骤：

1. `_split_beats` 把稿子切成语义拍，一句可多标（钩子/设问/数据/对比/列举/步骤/转折/机制/过程演示/强调/号召/金句…）。
2. **先按节拍白名单圈候选**（`BEAT_POOL`），再按「节拍 ×3 + 多标签 ×1.5 + 关键词 ×2 + 能量 ×0.6 − 重复 ×1.6」打分。纯关键词打分会把设问句配到堆叠条，所以语义白名单是硬前置。
3. **数据类有准入门**：句子必须有数字或量词；柱/环/折线/堆叠这类结构性图表还要求 ≥2 个数据点或明确的构成描述。一个「上千字」只配数字滚动，不许硬套一张堆叠条。
4. 置信度低于阈值 → **基础文字动效兜底**（逐字升起/柔焦/荧光笔/下划线…按最少使用轮转），注入口播原文；不塞复杂数据卡。
5. `--with-transitions` 每 N 拍（默认 3）插一个转场，不逐句插。

输出 `shots.json` 每拍含 `beat / text / fx / params / dur / at`。`render` 逐条渲成
`01_char_rise.mp4` … 并写 `manifest.json`；`emit` 直接产出项目镜头表代码。

## 项目接入

镜头表直接引用，不写实现：

```python
shots = [
    ("fx", {"fx": "bar_grow", "params": {"values": [20, 60, 90]}}, None, None, None, 1.0),
    ("fx", "char_rise", {"text": "同样一个 Muse"}, None, None, 1.0),
]
```

`make.py` 的 `("fx", ...)` 分支调 `runtime.render_clip`；`REELFORGE_HOME` 可指到
别的 skill 安装目录。也可完全绕开 `make.py`，用 `fx_pipeline.py render` 出片段再自己拼。

`runtime.ffmpeg_bin()` 依次找 `REELFORGE_FFMPEG` → PATH → `~/.local/bin` →
`C:/ffmpeg/bin` → `imageio_ffmpeg`。**实测某些 agent 会话 PATH 里没有 ffmpeg**，
只写 `"ffmpeg"` 会直接 `FileNotFoundError`；项目侧若要补 PATH，必须在
`import vid` 之前补（vid 会把当时的 `os.environ` 冻结成 `ENV`）。

## 转场类用法

```json
{"fx": "ink_spread", "kind": "transition", "dur": 0.55,
 "params": {"a": "shots/a.mp4", "a_at": 3.2, "b": "shots/b.png", "dur": 0.55}}
```

- `a` / `b` 可以是图片，也可以是视频（给 `a_at` / `b_at` 指定抽帧秒数）。
- 两端必须是**完整帧**，别用被裁短的视频输入，否则 `shortest` 会截断整条链。
- 白闪峰值别超过 0.12 秒；暗场别压到纯黑（留 0.04）；放大别超过 1.5 倍。

## 新增效果 checklist（缺一不可）

1. 写进 `effects/fx/<pack>.py`，遵守纯函数契约，参数全走 `params`。
2. 在 `effects/index.json` 登记 `entry / kind / status=ready / beats / auto / requires / pitfalls`。
3. `python scripts/fx_pipeline.py check` 全量自检，必须 0 异常。
4. 出基准帧（960×540 jpg）到 `effects/baselines/`，**看一眼总览图**确认版式，
   不是「文件生成了」就算验过。
5. 提交仓库 + 同步到各 agent 技能目录（见 `DEPLOY.md`）。

## 回归

改动已有效果后：重新出基准帧 → 与旧图做像素差（`scripts/similarity.py` 图片模式）
→ 差异超阈值就在配方卡里升 `version` 并注明原因。全库回归用
`python scripts/fx_pipeline.py check`。

## 卡片目录（catalog）

`skills/reelforge/catalog/` 随仓库分发外部成熟动效库的**索引**（不是代码）：

| 文件 | 来源 | 条数 | 许可 |
|---|---|---|---|
| `talkcraft.json` | video-talkcraft | 108 | PolyForm 非商业（自用无碍） |
| `shotcraft.json` | video-shotcraft | 124 | 代码 Apache-2.0 |
| `vocab.json` | talkcraft 节拍词表 | 26 类 | 同上 |

```bash
python scripts/effects.py catalog --beat 强调
python scripts/effects.py suggest --script script.md --inputs 图,截图 --top 3
```

`catalog/` 是**选型参考**，`effects/index.json` 才是**能跑的实现**。别把两者混为一谈：
卡片有 232 张，可运行效果目前 33 个，其余仍是候选。

## 常见坑

| 坑 | 现象 | 规则 |
|---|---|---|
| 只认本地 index | 仓库新增效果在本机看不见 | 两边合并，仓库优先 |
| `entry` 带冒号按整串当路径 | `check` 误报全部效果文件缺失 | 冒号后是函数名，取 `partition(":")[0]` |
| 标注类无底图 | 圈/线画在空纸上 | 传 `image`（截图）或 `text`（口播句），`_canvas` 会画文字兜底 |
| 拿 `target` 宽高当文字区 | `index_badge` 的 target 宽 0，句子被折成竖排单字串 | 文字用固定 `text_box`，别复用 target |
| 数据类无数据硬套 | 设问句配一张堆叠条 | 走 `plan` 的准入门，低置信回基础文字动效 |
| 改了效果但画面没变 | `render_clip` 看到文件存在就跳过 | `--force` 或删片段重渲 |
| ffmpeg 找不到 | `FileNotFoundError [WinError 2]` | 用 `runtime.ffmpeg_bin()`，别写死 `"ffmpeg"` |
