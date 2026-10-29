---
name: reelforge
description: 三端编排的短视频生产流水线。总控（本 skill）负责拆解、状态机、参考度审计与验收；写稿交给 reelforge-writer（任意强写作模型，如 Gemini 4 Argon）；出片交给 reelforge-runner（任意能执行命令的编码 agent，如 DeepSeek Harness）。支持「完全自定义主题」和「参考片最多 60%、默认 40%」两种模式，口播稿必须先确认再开工，成片为 16:9 网页视频（wvp）录屏。
---

# ReelForge

给一个主题或一条参考片，产出「拆解（可选）+ 口播稿 + 16:9 成片」。
**总控不做具体活**：它拆任务、盯状态、卡验收；写稿与出片各有专用 skill。

## 角色

| 角色 | 谁来做 | skill | 干什么 |
|---|---|---|---|
| 总控 | WorkBuddy / 任意编排 agent | `reelforge` | 拆解、组任务包、审计、验收、汇总 |
| 写稿 | 强写作模型（默认 Antigravity `gemini-4-argon-medium`，低思考） | `reelforge-writer` | `script.md` / `script.json` |
| 执行 | 编码 agent（默认 DeepSeek Harness，**官方来源** `deepseek-flash`＝V4.1 Flash，思考 max；可切 WorkBuddy 来源） | `reelforge-runner` | wvp 工程、章节、音频、录屏 |
| 出图 | 任意图像能力 | — | 封面、图表、插图 |

三端通过**文件 + `state.json`** 协作，谁都能换，只要读写同一份工作目录。
换 agent 的部署方法见 `DEPLOY.md` / `AGENT_DEPLOY.md`。

### 两种运行模式（并存，按场景切换）

| 模式 | 总控是谁 | 组成 | 适合 |
|---|---|---|---|
| **trio** | WorkBuddy（本 skill） | WorkBuddy + Antigravity + Harness/Codex | 批量、无人值守、手机上盯着 |
| **duo** | **人**（你在电脑前） | Antigravity + Harness/Codex（执行者兼总控，用 `reelforge-duo`） | 边看边调、一次性高质量 |

模式只影响「谁来派活、谁来问验收」，
门槛、脚本、素材库、参考度审计完全共用。切换：改 `config/pipeline.yaml` 的 `mode`。

- trio：见本文件
- duo：见 `reelforge-duo` 的 SKILL（执行者读它），人只负责拍板与转发

## 流程

```
0  intake      收主题/素材/是否参考 → state.py init
1  reference   可选：analyze.py 拆参考 → reference.json（结构/手法/禁用）
2  script      pack_task.py writer → 写稿 agent → script.md / script.json
3  audit       similarity.py（默认40，上限60）+ 🛑 script_gate 用户确认口播稿
4  build       make_wvp_inputs.py → pack_task.py runner → 执行 agent 跑 wvp
5  gates       🛑 chapter_gate 第1章 → 🛑 audio_gate 音频
6  record      人工 OBS 或 record.mjs
7  deliver     ffprobe 验收 → 🛑 final_gate → 交付 + state done
```

四道门（`script_gate` / `chapter_gate` / `audio_gate` / `final_gate`）**不能跳**；
用户明确说「不用看」才可跳过，并把原话写进 `state.json` 的 `gate_note`。

## 0 · 开工

```bash
python scripts/state.py init --work work/<slug> --title "片名"
```

有没有参考片：

| 模式 | 做法 | 参考度 |
|---|---|---|
| 自定义主题 | 跳过阶段 1，直接把主题给写稿 | 0 |
| 参考片 | `python scripts/analyze.py --url ... --out work/<slug>` | 默认 40，上限 60 |

参考度不是「感觉像」，是 `similarity.py` 算出来的：结构 60% + 文案重合 40%。
超 60 必须重写结构，不许只换词。

## 1 · 参考拆解（可选）

```bash
python scripts/analyze.py --url "https://..." --out work/<slug> --frames 24
```

产出 `evidence.md` / `evidence.json`。总控读 `evidence.md` 写 `reference.json`：

```json
{"borrow": {"structure": ["开场冲突", "三点拆解", "落点"], "devices": ["数字滚动"]},
 "avoid": ["原句", "同款片头"], "budget": 40}
```

`avoid` 是硬清单，写稿必须逐条避开。

## 2 · 写稿（交给 writer）

**检索与取证也归写稿 agent**：网页搜索、读链接、抓正文、做事实核对，
都由 writer 用它的浏览器能力完成并交回 `source_digest.md`（每条结论标出处）。
总控不代笔、不自己搜；需要素材与事实时写进任务包让 writer 一起带回来。

```bash
python scripts/pack_task.py writer --work work/<slug> --persona ace --budget 40
```

把 `work/<slug>/tasks/writer.md` 交给写稿 agent（MCP 或手动），要求它先读
`reelforge-writer` 的 SKILL 与规则。产出必须包含 `script.md`、`script.json`、
`writer-notes.md`。

## 3 · 审计 + 口播稿确认

```bash
python scripts/similarity.py --work work/<slug> --target 40 --max 60
```

- 退出码 2（超 60）：打回写稿，附 hint
- 0：把**口播稿摘要**发给用户确认（标题、拍数、预估时长、参考度、需要拍板的点）

```bash
python scripts/state.py gate --work work/<slug> --name script_gate \
  --artifacts work/<slug>/script.md
```

确认后：

```bash
python scripts/make_wvp_inputs.py --work work/<slug>   # → outline.md / article.md
```

## 4 · 出片（交给 runner）

```bash
python scripts/pack_task.py runner --work work/<slug> --theme <id> --mode A --team
```

执行 agent 按 `reelforge-runner` 的 P0–P5 走；第 1 章完成会写 `chapter_gate`，
音频完成写 `audio_gate`。总控只做三件事：**轮询、转发验收卡、批准后给下一步**。

## 5 · 状态与同步

`work/<slug>/state.json` 是唯一事实源：

```json
{"stage":"build","status":"awaiting_user","gate":"chapter_gate",
 "jobs":{"writer":"conv_x","runner":"job_y"},"artifacts":["..."],"history":[]}
```

- agent 每完成一个阶段就更新 state，然后**停**
- 总控用 MCP 的 `result` / `get_result` 拉结果，不靠 agent 主动推（MCP 是拉模型）
- 每次 gate 在会话里发**一张 ≤10 行的卡**：阶段 / 产物 / 验收结果 / 下一步
- 手机 App 看的是同一个会话，直接回「过」或「改哪里」

远程时总控可以只刷状态、不贴长文：

```bash
python scripts/state.py show --work work/<slug> --json
```

## 6 · 素材库（长期复用）

库默认在 `~/.reelforge/library`，`REELFORGE_LIBRARY` 可改。

```bash
python scripts/assets.py init
python scripts/assets.py add cover.png --tags brand,cover --source generated --license own
python scripts/assets.py search --tag gpu --type image
python scripts/assets.py materialize --work work/<slug> --query gpu
python scripts/assets.py stats
```

- 入库按 sha256 去重，同一文件只存一份
- 每条记 `source / license / origin / used_in`，交付时能出授权清单
- `materialize` 会把文件复制进 `presentation/public/assets/` 并写 `assets.json`
- 出图 agent 产出后**先入库再投放**，下一条片子直接搜，不用重画

## 目录

```
work/<slug>/
  state.json                 三端共用状态机
  tasks/{writer,runner}.md   任务包
  reference.json             借什么/避什么/预算
  script.md script.json      writer 产出
  outline.md article.md      wvp 输入
  assets.json                素材清单
  presentation/              wvp 工程
    src/chapters/<id>/narrations.ts
    public/audio/<id>/<step>.mp3
    out/final.mp4
```

## 红线

1. **口播稿先确认**：`script_gate` 没过，不许 scaffold。
2. **参考度 ≤60**：`similarity.py` 退出码 2 就是硬失败。
3. **文案原创**：结构可借，句子不能借。
4. **四道门不跳**：每道门都要 `state.py gate` + 用户确认。
5. **执行 agent 不改稿**：要改稿回 writer，改完重新审计 + 再确认。
6. **16:9 固定**：wvp 只做 1920×1080，竖屏需求在 intake 就拒掉或换工具。
7. **不写回 skill 目录**：产物只在 `work/`。
8. **素材必须有授权字段**：`license=unknown` 的素材不能进成片。

## 常见故障

| 现象 | 处理 |
|---|---|
| 写稿 agent 交的稿超 60% | 附 `similarity.py` 的 hint 打回，要求换结构 |
| 执行 agent 停在某阶段不动 | `state.py show` 看 stage；检查 job 状态，必要时 `continue_session` |
| dsh 没起团队 | 确认 `@nanmicoder/dsh-agent-teams` 已装，任务以 `/agent-teams ` 开头 |
| Antigravity 模型档位不对 | MCP 只认 `flash`/`flash_lite`/`pro`，要用 Argon 需改桥接 enum，见 DEPLOY.md |
| 音频和 step 对不上 | 改过 `narrations.ts` 没重跑 extract/synthesize |
| 录屏没声音 | Playwright 不录系统声；用 `mix_audio.py` 拼轨后 `--audio`，或人工 OBS |

## 参考

| 文件 | 用途 |
|---|---|
| `references/orchestration.md` | 三端编排、轮询、验收卡模板 |
| `references/asset-library.md` | 素材库 schema 与工作流 |
| `references/script-contract.md` | `script.json` 契约 |
| `references/wvp-handoff.md` | wvp 六阶段操作 |
| `references/tts.md` | IndexTTS 服务与 provider |
| `references/analysis.md` | 拆解口径 |
| `DEPLOY.md` / `AGENT_DEPLOY.md` | 换 agent、换模型的部署方法 |
