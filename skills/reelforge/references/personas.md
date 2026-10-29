# 人设配置

预设了两个账号，给别的 agent 用、或者开源给别人用时，改一个 YAML 就能换成自己的号。

## 文件

| 文件 | 作用 |
|---|---|
| `config/personas.yaml` | 随 skill 分发的预设（两个账号） |
| `config/personas.local.yaml` | 可选，存在时**优先读它**，升级 skill 不会被覆盖 |

```bash
# 看当前用哪份配置、有哪些号
python scripts/personas.py --list

# 看某个人设全文 / 只要写稿 prompt 段落 / 只要音色
python scripts/personas.py --show ace
python scripts/personas.py --prompt ace     > persona_block.txt
python scripts/personas.py --voice ace
```

## 字段

```yaml
version: 1
default_persona: ace          # 不指定时用哪个

personas:
  ace:
    display_name: 阿测
    account_type: long_term   # long_term / traffic，仅作标记
    aliases: []               # 备选账号名
    positioning: 一句话定位
    personality: [好奇, 较真, 说人话]
    values:                   # 写稿时要守的价值观，逐条列
      - 有增量才发
    language: 语言风格
    catchphrases: ["先说结论"]  # 口头禅，写稿时自然带入，不要每句都塞
    banned: ["家人们"]          # 硬禁词，出稿后自检
    voice:
      provider: edge
      voice: zh-CN-YunxiNeural
      rate: "+8%"
      pitch: "+0Hz"
    visual:
      palette: ["#1D4ED8", "#FFFFFF"]
      avatar: 角标形象
      cover: 封面规则
    prompt_block: |           # 直接拼进反重力 prompt 的段落
      ……
```

## 写自己的号

1. 复制 `config/personas.yaml` → `config/personas.local.yaml`
2. 改 `display_name` / `positioning` / `values` / `catchphrases` / `banned`
3. 改 `prompt_block`：写清「他是谁、怎么说话、绝不说」
4. 换音色：`python -m edge_tts --list-voices | grep zh-CN`，填进 `voice.voice`
5. `python scripts/personas.py --list` 确认读到了 local 文件

## prompt_block 怎么写

**写人，不写台词模板。** 台词模板会让所有视频一个腔调。好的写法是：

- 身份与处境（他为什么懂这些）
- 三条价值观（判断标准，不是口号）
- 语言底色（句长、人称、术语怎么处理）
- 2–3 句态度锚点（不是开场白）
- 「绝不说」清单

反面例子：`开场必须说"大家好我是XX"`——这是模板，不是人设。

## 两个账号为什么要区隔

预设里两个号的名字、音色、视觉色、口头禅都不同，公开层面互不提及。
这是账号运营策略（风险隔离），也是写稿时的硬约束：**不要把两个号的语气混用**。
