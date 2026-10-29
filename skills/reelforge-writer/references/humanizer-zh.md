# humanizer-zh 接入（可选）

本 skill **不内置** humanizer-zh。它和 `writing-rules.md` 第三节（五类 AI 腔）
有重叠，装了之后按下面任一方式叠加：

## 方式 A：环境变量指路

```bash
export REELFORGE_HUMANIZER="$HOME/.workbuddy/skills/humanizer-zh/SKILL.md"
```

写稿前读这个文件，把里面的禁用词表和改写示例当附加约束。

## 方式 B：复制规则

把 humanizer-zh 的「禁用词 / 改写示例」两节粘到本文件末尾，作为项目内规则。

## 冲突时怎么办

- 结构、字数、画幅：以 `writing-rules.md` 为准
- 用词、腔调：以 humanizer-zh 为准（它更细）

装好之后在 `writer-notes.md` 里写一行「humanizer: on/off」，方便回溯。
