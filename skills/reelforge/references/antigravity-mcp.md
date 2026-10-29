# 反重力写稿：MCP 调用规范

Antigravity 的能力**只能**通过 MCP 工具调用。不要写 Python 直连 `agentapi`，
不要用 `--model` 透传参数——那条路已经废弃。

## 工具

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `mcp__antigravity__health` | 开工前探测桥接是否可用 | 无 |
| `mcp__antigravity__start_session` | 新建异步会话，立即返回 `conversation_id` | `prompt`（必填）、`model`、`title` |
| `mcp__antigravity__get_result` | 等会话完成，拿最终回复 | `conversation_id`、`timeout`（默认 900s） |
| `mcp__antigravity__analyze_video` | 让它直接看一段本地视频 | `path`、`instruction`、`frames`、`model` |
| `mcp__antigravity__list_sessions` | 查会话状态（超时后先查再拉） | 无 |

模型档位只有三档：`flash_lite`（最快）、`flash`（默认）、`pro`（推理更强）。
写稿用 `flash`；需要长链推理或复杂约束时用 `pro`。没有 medium 档，MCP 不暴露。

## 两步调用

### 1. 开会话

```
mcp__antigravity__start_session(
  title = "scripts: <片名>",
  model = "flash",
  prompt = <下面的模板>
)
→ {"conversation_id": "..."}
```

### 2. 取结果

```
mcp__antigravity__get_result(conversation_id = "...", timeout = 900)
→ 最终回复文本
```

超时不要重开会话：先 `list_sessions` 确认还在跑，再 `get_result` 拉一次。
连续两次失败就停下来告诉用户，不要自己编脚本。

## Prompt 模板

把 `<...>` 替换成实际内容。**拆解摘要要具体到时间点**，不要写「节奏快」这种空话。

```text
你是中文短视频的口播作者。基于下面的拆解，为这条新片写脚本。

【参考片拆解】
<把 analysis.md 的八节浓缩成 15 行以内：钩子手法、结构、信息密度、视觉语法、语速、可复用装置、不能学的>

【本次主题与素材】
主题：<...>
必须出现的信息：<卖点/参数/结论，逐条列>
可用素材：<本地截图/录屏路径，或"纯代码图形">
目标时长：<N> 秒（硬约束）
画幅：16:9 横屏（固定，wvp 只做 1920×1080）

【账号人设】
<语气、身份、立场；一句"不喊单不标题党"这类底线>

【硬约束】
1. 一共 <N> 拍，第 1 拍是钩子，3 秒内落地
2. 总字数 <X–Y> 个汉字（按 5 字/秒估算，超了会超时）
3. 每拍 text 按标点切开后，任意一段不超过 14 个汉字（16:9 一屏一行能读完）
4. 只能用【必须出现的信息】里的数字，绝对不许自己造数字或百分比
5. 不用"最/第一/必买/全网"这类绝对化用词
6. 不出现购买引导、联系方式、加群

【输出】
只输出 JSON，不要解释、不要 markdown 代码块，结构：
{"title":"","duration_sec":N,"aspect":"16:9","beats":[{"id":"s1","text":"","visual":"","duration_sec":3.0}]}

其中 visual 写「观众要看懂什么变化、主体前后状态」，不写"淡入""缩放"这类效果名。
```

## 返回处理

1. 去掉可能的 ```json 围栏，取第一个 `{` 到最后一个 `}`。
2. `json.loads`；失败就把报错和原文片段发回同一会话让它修（`start_session` 新开会话时
   带上原文 + 报错），最多一次。
3. 通过 `references/script-contract.md` 的校验后写 `work/<slug>/script.json`。
4. 校验不通过（时长偏差 >15%、某拍缺 visual）时，先自己按规则修明显项，
   修不了的列给用户，不要静默改内容。

## analyze_video（可选）

长视频或需要语义级理解时用：

```
mcp__antigravity__analyze_video(
  path = "D:/work/<slug>/source.mp4",
  instruction = "按时间点列出：每段的画面主体、动作、出现的文字；标出所有产品名与数字",
  frames = 24,       # 0 = 直接喂原视频（仅短视频）
  model = "flash"
)
```

它给的是**语义摘要**，时间点会有秒级漂移；和本地转写/切点冲突时，以本地为准。

## 禁止

- ❌ 写脚本 `import server` 直调（旧 `ag_write.py` 的路子）
- ❌ 用 `--model gemini-3.8-flash-medium` 这类透传
- ❌ Antigravity 不可用时用模板文案/占位内容顶替
- ❌ 把 MCP 返回的 JSON 原样当最终稿，不经校验就进渲染
