# 素材库

wvp 本身**没有**跨片子的素材库：它只在 `outline.md` 末尾列本片素材清单，
工程里用 `public/assets/`。所以长期做片会重复找图、重复生成、授权也说不清。

reelforge 补这一层：一个本地库 + 一套投放命令，所有片子共用。

## 1. 位置

```
~/.reelforge/library/            # REELFORGE_LIBRARY 可覆盖
  index.json
  files/image/img_a23ec0fe.png
  files/video/vid_...
  files/audio/aud_...
```

## 2. index.json

```json
{
  "version": 1,
  "updated_at": "2026-10-29T17:35:54+08:00",
  "items": [
    {
      "id": "img_a23ec0fe",
      "kind": "image",
      "path": "files/image/img_a23ec0fe.png",
      "original_name": "gpu_chart.png",
      "sha256": "a23ec0fe...",
      "bytes": 18233,
      "width": 640, "height": 360,
      "duration_sec": null,
      "source": "generated",
      "origin": "ImageGen prompt: ...",
      "license": "own",
      "tags": ["chart", "gpu"],
      "note": "跑分对比图",
      "created_at": "...",
      "used_in": ["demo"]
    }
  ]
}
```

字段规矩：

| 字段 | 规矩 |
|---|---|
| `source` | `user` / `generated` / `downloaded` |
| `license` | `own` / `CC0` / `CC-BY` / `CC-BY-SA` / `unknown` |
| `origin` | 生成的写 prompt 摘要，下载的写 URL |
| `used_in` | 由 `materialize` 自动追加，不手改 |
| `sha256` | 去重唯一依据，同名不同内容也算两条 |

`license=unknown` 的素材**不能进成片**（红线第 8 条）。

## 3. 命令

```bash
python scripts/assets.py init
python scripts/assets.py add <file> [--type image] [--tags a,b] \
       [--source generated] [--license own] [--origin "..."] [--note "..."]
python scripts/assets.py search [--query x] [--tag a,b] [--type image] [--limit 20] [--json]
python scripts/assets.py materialize --work work/<slug> [--ids id1,id2 | --query x | --tag a]
python scripts/assets.py stats
python scripts/assets.py scan        # 检查文件丢失/重复
python scripts/assets.py prune       # 列出没被任何片子用过的
```

`materialize` 做三件事：

1. 复制到 `<work>/presentation/public/assets/<id>.<ext>`
2. 写/更新 `<work>/assets.json`（交付时的授权清单）
3. 回写 `used_in`

## 4. 和写稿、执行怎么配合

| 阶段 | 用法 |
|---|---|
| 写稿 | 读 `assets.json` 和 `assets.py search` 结果，画面描述里优先用已有素材 |
| outline | 素材清单写库 id，不写「找一张 GPU 图」 |
| 执行 | `assets.py materialize` 一次投放，章节代码用 `public/assets/<id>` |
| 出图 | 新图先 `add` 入库，再 `materialize`，保证下一条片子能复用 |
| 交付 | 把 `assets.json` 的 `license/origin` 附进交付清单 |

## 5. 长期维护

- 每月 `stats` 看体积；`prune` 列出的素材确认半年没用再考虑归档（不要直接删）
- 品牌资产（logo、字体、片头）打 `brand` 标签，优先级最高
- 同一主题的图打同一组标签（`gpu`、`benchmark`、`price`），检索才快
- 生成的图保留 prompt 摘要，方便下次改一版而不是重画

## 6. 为什么不做成第四个 skill

素材库没有独立的判断逻辑，它就是总控的一个数据层：
写稿要查、执行要投放、交付要列授权。拆成 skill 只会多一层跳转。
所以它是 `reelforge/scripts/assets.py` + 本文档。
