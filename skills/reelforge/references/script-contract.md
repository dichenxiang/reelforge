# script.json 契约（写稿阶段专用，瘦身版）

写稿 agent 只交**写稿需要的东西**。视觉风格、配色、动效、镜头、BGM 这些
是**出片阶段**由 wvp 的 direction 决定的，不在这里，别为了填字段而写稿。

> 人设不在这个文件里，在 `config/personas.yaml`。写稿前必须先读人设（见下）。
>
> **口播风格不在这里，也不在我们的 writing-rules 里**：
> 以 `vendor/web-video-presentation/references/SCRIPT-STYLE.md` 为唯一权威。
> 本文件只是把「写完之后落成什么结构」定下来。

## 先读人设（必做）

```bash
python <reelforge>/scripts/personas.py --prompt ace     # 或 gatekeeper
```

打印出来的是这个账号的说话方式、价值观、态度锚点句和**禁词表**。
稿子必须像这个号说的话，且不得出现禁词。写完自己再扫一遍禁词。

## 结构

```json
{
  "title": "Muse 会替你操作浏览器，但也会被风控盯上",
  "duration_sec": 40,
  "aspect": "16:9",
  "platform": "抖音 / 视频号",
  "takeaway": "它很强，但封号是真实成本",
  "hook": "第一句就把封号这件事砸出来",
  "ending": "落版：先小号试，别拿主号赌",
  "source_basis": "2 条 x.com 帖 + 官方说明；哪些结论是推断已标注",
  "beats": [
    {
      "id": "s1",
      "text": "第一拍念出来的话",
      "visual": "这一拍观众看懂什么变化（写变化，不写元素）",
      "duration_sec": 4.0
    }
  ]
}
```

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | ✅ | 片子标题 |
| `duration_sec` | ✅ | 目标时长（≤1200） |
| `aspect` | ✅ | 固定 `16:9`（wvp 硬约束） |
| `beats[].id` | ✅ | `s1`、`s2`… 顺序编号 |
| `beats[].text` | ✅ | 口播原文；一屏 ≤14 个汉字 |
| `beats[].visual` | ✅ | 观众看懂什么变化 |
| `beats[].duration_sec` | ✅ | 这拍多长；Σ 与 `duration_sec` 偏差 ≤15% |
| `takeaway` | ✅ | 一句话结论 |
| `platform` | | 投放平台 |
| `hook` | | 第一句的冲突点 |
| `ending` | | 落版那句话 |
| `source_basis` | | 资料来源；推断要标出来 |
| `notes` | | 写给执行者的提醒 |

## 不在写稿阶段的东西

`style` / `palette` / `type` / `motion` / `camera` / `texture` / `brand` /
`benchmark` / `bgm` / `sfx` / `tts` / `forbidden` / `structure` —— 这些由
**出片阶段**决定（wvp 选主题 + direction + 章节 craft），写在稿子里只会
让写稿 agent 瞎填。

需要控制的地方写 `notes` 里，例如「这句别上屏」「这里要留一个数据对比」。

## 配套文件

| 文件 | 谁写 | 内容 |
|---|---|---|
| `source_digest.md` | 写稿 agent | 检索结果与出处 |
| `script.md` | 写稿 agent | 口播稿，`---` 切节拍，节拍数 = beats 数（风格按 wvp SCRIPT-STYLE） |
| `outline.md` | 写稿 agent | 开发计划，按 wvp `OUTLINE-FORMAT.md` 写 |
| `script.json` | 写稿 agent | 本文件 |
| `writer-notes.md` | 写稿 agent | 借鉴清单、自评参考度、首行 `writer-agent: <名字>` |

## 校验规则（人工/脚本自检）

| 项 | 规则 | 不满足 |
|---|---|---|
| 总时长 | Σ`beats[].duration_sec` 与 `duration_sec` 偏差 ≤15% | 报 warning |
| 拍数 | 8–20 秒 4–8 拍；>20 秒按 3–4 秒/拍 | 人工判断 |
| 口播字数 | 中文 5 字/秒；`duration_sec × 5 × 1.1` 为上限 | 超了会爆时长 |
| 单拍 text | 每段 ≤14 个汉字（16:9 一屏一行能读完） | 屏幕上读不完 |
| aspect | 只接受 `16:9` | 报错，改稿或换工具 |
| 禁词 | 人设的 `banned` 一个都不能出现 | 平台限流风险 |
| 数字 | 只能来自用户、检索结果或可查来源 | 事实错误 |
| 用词 | 无「最/第一/必买/全网」 | 平台限流风险 |

## 屏幕文字量怎么控制

wvp 是 1920×1080、每步独占整屏。一屏一行大字 + 一行辅助说明最稳：
主标题 ≤14 个汉字，副标 ≤20 个，超过就拆成两个 step。
英文/数字按半宽折算：`GPT-6.1` 算 7 个宽度单位。
拆点优先落在标点，其次在「的/了/在」前后，不要拆开数字和英文单词。
