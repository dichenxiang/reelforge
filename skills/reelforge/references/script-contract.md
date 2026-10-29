# script.json 契约

反重力的输出不直接进渲染，先收敛成这个结构，人工确认后才用。

## 结构

```json
{
  "title": "GPT-6.1 Terra 为什么只卖一半价",
  "duration_sec": 18,
  "aspect": "16:9",
  "platform": "抖音 / 视频号",
  "format": "product-explainer",
  "takeaway": "中端价格，旗舰一半的跑分",
  "hook": "第一句就把价格差拍出来",
  "signature": "第 9 秒：跑分条从旧值滚到新值，落定同时出'翻倍'",
  "structure": {
    "chosen": "价格差 → 跑分对比 → 短板 → 一句话结论",
    "candidates": ["价格差先行", "跑分先行", "短板先行"]
  },
  "style": {
    "name": "swiss-editorial",
    "signals": ["大字号左对齐标题", "细网格线", "单一强调色"],
    "avoid": ["深色背景", "紫蓝渐变", "居中大字"]
  },
  "benchmark": {"name": "参考片", "learn": "切点密度与信息节奏", "avoid": "文案与镜头"},
  "brand": "主色 #E4572E，字体思源黑体",
  "palette": "背景 #F5F1E8 / 主色 #111 / 强调 #E4572E",
  "type": "展示 思源黑体 Heavy / 辅助 Regular",
  "motion": "snap 入场，无弹簧",
  "camera": "固定机位 + 元素位移",
  "texture": "纸纹 5%",
  "sound": "轻电子，80 BPM，无鼓点冲击",
  "bgm": "AI 合成",
  "sfx": "AI 合成，只在数字落定处",
  "tts": "本地 IndexTTS 2.0 / 人设 ace / 参考音频 D:/indexTTS/voices/ace_ref.wav",
  "forbidden": ["跑马灯", "每拍都放大", "念字幕"],
  "beats": [
    {
      "id": "s1",
      "text": "同一档跑分，价格只要一半。",
      "visual": "旧价与新价两个数字同屏，新价压住旧价",
      "duration_sec": 3.2,
      "state": "两个价格从并排到新价放大",
      "carry": "价格卡延续到下一拍",
      "event": "0.6s 新价落定",
      "audio": "合成器单音，落定处一个 click",
      "transition": "价格卡右移出画"
    }
  ],
  "ending": "落版定格：一句话结论 + 账号名",
  "duration_note": "无",
  "source_basis": "参考片拆解 + 厂商公布参数"
}
```

## 必填

`title` `duration_sec` `aspect`（**固定 `16:9`**，wvp 只做 1920×1080）
`beats[]`（每拍 `text` + `visual` + `duration_sec`，一拍 = wvp 一个 step）
`style.name` `takeaway` `hook`
`bgm` `sfx`（来源必须是用户确认过的：`AI 合成` / `用户提供：<路径>` / `关闭`）

`progress_preview`：`启用` / `未提出`（用户要不要看制作过程，对应上游进度页）。

## 校验规则（写稿时自检；make_wvp_inputs.py 只做格式转换）

| 项 | 规则 | 不满足 |
|---|---|---|
| 总时长 | Σ`beats[].duration_sec` 与 `duration_sec` 偏差 ≤15% | 报 warning，退出码 2 |
| 拍数 | 8–20 秒片子 4–8 拍；>20 秒按 3–4 秒/拍 | 人工判断 |
| 口播字数 | 中文按 **5 字/秒** 估算；`duration_sec × 5 × 1.1` 为上限 | 超了会爆时长 |
| 单拍 text | 每段 ≤14 个汉字（16:9 一屏一行能读完） | 屏幕上读不完 |
| aspect | **只接受 `16:9`**（wvp 固定 1920×1080） | 报错，改稿或换工具 |
| 数字 | 只能来自用户或可查来源 | 事实错误 |
| 用词 | 无「最/第一/必买/全网」 | 平台限流风险 |

## 屏幕文字量怎么控制

wvp 是 1920×1080、每步独占整屏。一屏一行大字 + 一行辅助说明最稳：
主标题 ≤14 个汉字，副标 ≤20 个，超过就拆成两个 step。
英文/数字按半宽折算：`GPT-6.1` 算 7 个宽度单位。
拆点优先落在标点，其次在「的/了/在」前后，不要拆开数字和英文单词。

## 修稿顺序

1. 先砍字数（删形容词、删重复结论），不动信息点
2. 再调拍长（把长拍拆成两拍，或合并碎拍）
3. 最后才改结构

改完必须让用户确认新版本；`narration.txt` 一旦生成就只读，TTS 只能读它。
