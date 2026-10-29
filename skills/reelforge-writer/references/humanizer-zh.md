# humanizer-zh 接入（可选）

「去 AI 味」的中文 skill。**它不是写作规范，是写完之后的清洗工序。**

## 仓库地址

```
https://github.com/op7418/Humanizer-zh        ← 中文版主仓库（推荐）
https://github.com/blader/humanizer           ← 英文原版 v3.0.0（源头）
https://github.com/hardikpandya/stop-slop     ← 另一个参考来源
https://github.com/nothing0here/humanizer-zh  ← 另一个中文 fork
```

## 安装

```bash
# 全局装（skills CLI 会自动认 agent）
npx skills add https://github.com/op7418/Humanizer-zh.git

# 或手动
git clone https://github.com/op7418/Humanizer-zh.git \
  ~/.workbuddy/skills/humanizer-zh
```

装好后本 skill 会自动认它；也可以显式指定：

```bash
export REELFORGE_HUMANIZER="$HOME/.workbuddy/skills/humanizer-zh/SKILL.md"
```

## 它是什么

- **31 条模式**，分 6 组：A 铺垫代替陈述 / B 公式化节奏 / C 拔高与借权威 /
  D 公式化排版 / E 聊天与草稿残留 / F 中文表达补充检查
- 核心约束：**保留信息与确定程度**（不新增事实、不把「可能」改成「确定」）、
  匹配作者声音、不替作者编经历
- 注意版本：2026-09-23 之后是重写版（31 条 + 更严的边界）；之前是 24 条旧版

## 和 wvp SCRIPT-STYLE 的关系（重要）

两者同源（都出自 Wikipedia《Signs of AI writing》），所以**内容高度重叠**：

| | SCRIPT-STYLE 的「去 AI 味五类」 | humanizer-zh |
|---|---|---|
| 作用位置 | 写稿过程里就按它写 | 写完之后做清洗 |
| 覆盖 | 5 类腔调，口播向 | 31 条模式，中文向（含公文/技术文） |
| 冲突点 | — | 「不要为了短句把连贯文章拆成要点提纲」 |

**用法**：口播稿先按 SCRIPT-STYLE 写完（三层自检通过后），再过一遍 humanizer-zh
做最后清洗，且**只清洗句子、不重写结构**——它会把「--- 分节拍」当成排版问题处理。
所以给它下指令时必须说：

> 只改句子层面的 AI 痕迹，保留 `---` 分节拍、保留每拍的口语节奏、不要把
> 节拍合并、不要改数字和结论、不要补充原文没有的信息。

## 冲突时谁优先

1. **结构 / 画幅 / 禁词 / 参考度** → 我们的约束
2. **像不像口播** → wvp SCRIPT-STYLE
3. **像不像人写的** → humanizer-zh
4. **像不像本号** → `patterns-gatekeeper.md` / `patterns-ace.md`
