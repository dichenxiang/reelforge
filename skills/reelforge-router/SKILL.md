---
name: reelforge-router
description: 用户要做/改短视频、产品宣传片、口播视频、知识视频，或把文章/主题/参考片做成视频时，先读这个技能。它把任务路由到 reelforge（流水线，可单 agent 全包）、reelforge-duo（人在前）、reelforge-writer（只写稿）、reelforge-runner（只出片），并强制先问四件事：人设、路线 A/B、配音方式、字幕交付。
---

# ReelForge 路由（先读我）

只要用户的任务是「做一条视频 / 把这篇内容做成视频 / 照着这个片子做 / 写个口播稿」，
先按下面路由，不要直接开始写稿或写代码。

## 1. 先判断角色

| 用户场景 | 读哪个 skill |
|---|---|
| 人在电脑前，边看边调，人拍板 | `reelforge-duo/SKILL.md`（duo 模式） |
| 无人值守、批量、手机盯 | `reelforge/SKILL.md`（trio 模式） |
| 只要口播稿，不做视频 | `reelforge-writer/SKILL.md` |
| 已有稿子，只要出片 | `reelforge-runner/SKILL.md` |

路径：`<skills>/reelforge*/`。执行前先跑一次依赖体检：

```bash
python <skills>/reelforge-runner/scripts/preflight.py
```

## 2. 强制先问（缺一不可，别默认）

1. **用哪个人设**：`personas.py --list` 列出来让用户选；没有就 `personas_init.py` 建，**不要预设“阿测/学长”**
2. **出片路线**：A = 网页章节 + 录屏（默认）；B = EAC `motion-promo-film` 的 `__seek(t)` 时间轴（需装 EAC 插件）
3. **配音**：IndexTTS 预设 / 参考干声 / edge-tts / 自定义；有 IndexTTS 先 `tts_once.py --list-presets` 让用户选
4. **字幕**：烧录 / 外挂 SRT / 不要（默认烧录）

答案写进 `state.json`：
`state.py set --work <work> --meta render=A --meta template=<id> --meta tts_provider=... --meta tts_preset=... --meta subs=burn`

## 3. 四道门（不能跳）

```
state init → pack_task writer → 写稿 agent → similarity 审计 → 🛑 script_gate
→ 选路线/模板/配音/字幕 → pack_task runner → 第 1 章/首段 → 🛑 chapter_gate
→ 音频 → 🛑 audio_gate → 录屏/混音/字幕 → ffprobe + 抽帧 → 🛑 final_gate
```

- 写稿 agent 开工前必须问：人设 / 目标 / 受众 / 素材
- 关键画面拿不到时，先判断能否公开检索；**能搜到的不麻烦用户**，只能实拍/录屏的才向用户要，并给替代方案
- 真实产品操作必须录屏；示意图要标注“示意”

## 4. 出片工具（路线 A）

```bash
# 用生产构建录屏（不要用 dev server）
node <skills>/reelforge-runner/scripts/record_auto.mjs --url "http://127.0.0.1:4176/?auto=1" --duration <片长+15> --out out/raw.webm
python <skills>/reelforge-runner/scripts/mix_timeline.py --raw out/raw.webm --timeline out/raw.timeline.json --segments audio-segments.json --audio-dir public/audio --out out/final.mp4 --burn --srt out/final.srt
```

路线 B 读 `<skills>/reelforge-runner/references/route-b-eac-film.md`。

## 5. 红线

- 不改写用户已确认的稿子；要改回写稿 agent
- 不编造素材、数据、政策；查不到写“未证实”
- 不用 Windows SAPI（机械音）
- 没跑完 ffprobe + 抽帧验收，不说“交付完成”
- 不提交任何密钥/账号文件
