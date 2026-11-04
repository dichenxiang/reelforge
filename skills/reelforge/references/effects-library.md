# 效果库（跨片子复用动效）

素材库解决"图片视频别重复找"，**效果库解决"动效别重复写"**。两者是并列的长期资产，都放在 `~/.reelforge/`。

## 位置与统一策略

```
~/.reelforge/
  library/     素材：图片 / 视频 / 音频（见 asset-library.md）
  effects/     效果：动效模块（本文档）
```

- 默认路径 `~/.reelforge/effects`，环境变量 `REELFORGE_EFFECTS` 可覆盖。
- **换 agent 不丢的三条**：
  1. 路径由 `scripts/effects.py where` 解析，任何 agent 都先跑这一句拿绝对路径，不自己拼。
  2. `index.json` 里写死 `root` 绝对路径，换机器时一眼看出库在哪。
  3. 开工时把解析结果写进 `state.json` 的 `effects_root`，后续所有环节读它，不读环境变量。
- **禁止**把效果只写在项目目录里而不入库。项目里的临时实现，交付前必须 `register` 进库。

## 目录结构

```
~/.reelforge/effects/
  index.json                清单（含 root 绝对路径）
  fx/<id>.py                效果模块
  baselines/<id>.png        基准帧（回归对比）
  previews/<id>.png         最近一次预览
```

`index.json` 条目：

```json
{
  "id": "frame_zoom",
  "title": "屏幕边框 + 原位高亮 + 悬浮放大条",
  "desc": "...",
  "tags": ["zoom", "screen", "magnifier"],
  "entry": "fx/frame_zoom.py",
  "baseline": "baselines/frame_zoom.png",
  "used_in": ["muse-skill-video"],
  "updated_at": "2026-11-04T22:10:00+08:00"
}
```

## 模块契约（无例外）

```python
DEFAULT_PARAMS = {...}

def render(t: float, total: float, params: dict | None = None) -> Image.Image:
    """返回 1920×1080 RGB。禁止读外部状态，一切可变项走 params。"""
```

- 纯函数：同样的 `(t, total, params)` 必然得到同一帧。
- 不依赖项目里的字体、纸张、调色板——需要就放进 `params`，或在模块内自带默认。
- 不写文件、不发请求、不读全局变量。

## 命令

```bash
python scripts/effects.py init                     # 建库
python scripts/effects.py where                    # 打印绝对路径（换 agent 先跑这个）
python scripts/effects.py new <id> --title "..." --tags a,b
python scripts/effects.py register ./fx_tmp.py --id <id> --title "..." --tags a,b
python scripts/effects.py list [--tag zoom]
python scripts/effects.py path <id>
python scripts/effects.py baseline <id> --at 1.4 --params '{"image":"..."}'
python scripts/effects.py check                    # 缺文件 / 缺基准帧
```

## 入库规则

**什么算"新动效"**：任何在本片里新写的、单帧可描述的动画/版式（放大镜、稿纸堆、人物气泡、输入框、终端窗口、报头、印章…）。

交付前必须：

1. `register` 进库，补 `title / tags / desc`
2. `baseline` 出一张基准帧
3. 在 `used_in` 里记片子 slug

**什么不算**：素材本身（进素材库）、字幕条（属于 core/subtitle）、一次性的转场参数调整。

## 回归

改动已有效果后：

1. `baseline <id>` 重新出一帧
2. 和旧图做像素差（或 `scripts/similarity.py` 的图片模式）
3. 差异超阈值就说明改了版式，要在 `index.json` 里升 `version` 并注明原因

## 与流水线的关系

镜头表里直接引用，不写实现：

```json
{"fx": "frame_zoom", "params": {"image": "shots/b.png", "focus": [140, 318, 940, 132]}, "seconds": 4.2}
```

runner 侧只做三件事：读 `effects_root` → `effects.py path <id>` → import 调 `render`。
