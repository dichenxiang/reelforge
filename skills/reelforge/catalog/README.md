# 卡片目录（随仓库分发）

这些是**外部动效库的索引**，不是代码。放在仓库里，是为了换机器 / 换 agent 时卡片库不丢。

| 文件 | 来源 | 条数 | 许可 |
|---|---|---|---|
| `talkcraft.json` | [video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft) | 108 | PolyForm Noncommercial 1.0.0（个人/教育/研究免费，商业需授权） |
| `shotcraft.json` | [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 124 | 代码 Apache-2.0 |
| `vocab.json` | 同上（talkcraft 的节拍词表） | 26 类 | 同上 |

**用途**：`scripts/effects.py` 的 `catalog` / `suggest` 靠它做选型。这是**只读索引**，不含对方的实现代码；真正出画面要靠我们自己实现，或用对方工具导出透明通道素材。

**读取顺序**：
1. `$REELFORGE_EFFECTS/catalog/`（本地库，默认 `~/.reelforge/effects/catalog`）
2. 本目录（仓库自带）

同一条目（source + id）只保留一份，本地的优先级更高，方便你改本地覆盖。

**刷新**（上游更新时）：

```bash
# talkcraft
curl -sL https://raw.githubusercontent.com/Vincentwei1021/video-talkcraft/main/references/cards-index.json -o tc.json
# shotcraft
curl -sL https://raw.githubusercontent.com/Vincentwei1021/video-shotcraft/main/gallery/api/library.json -o sc.json
```

拿到后用 `scripts/effects.py` 的字段映射重新生成（`id/title/intent/category/energy/beats/inputs/source/ref`）。

**商业使用注意**：talkcraft 条目来自非商业许可的仓库，仅作个人参考索引；若将来商用或对外分发，需先处理该许可，或只保留 shotcraft / 自研卡片。
