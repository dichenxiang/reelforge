---
name: reelforge
description: 模块化短视频生产流水线（总控/写稿/执行三部分，可一个 agent 全包）。总控（本 skill）负责拆解、状态机、参考度审计与验收；写稿交给 reelforge-writer（任意强写作模型，如 Gemini 4 Argon）；出片交给 reelforge-runner（任意能执行命令的编码 agent，如 DeepSeek Harness）。支持「完全自定义主题」和「参考片最多 60%、默认 40%」两种模式，五道门强制（风格→口播稿→样片→音频→成片），成片为 16:9，四条出片路线：A=wvp 网页录屏 / B=EAC film `__seek(t)` / C=Pillow 离线逐帧+FFmpeg（实战验证）/ D=wvp+EAC 混合；选完必须写进 state，不许把 C 说成 A 或 B。内置 33 个可运行动效与 232 张配方卡，用 fx_pipeline.py 按口播稿自动匹配动效并渲染片段（plan/render/emit/check）；凡是做视频、加动效、字幕动画、转场、数据图表、放大镜高亮，一律先查效果库，不要手写动效。
---

# ReelForge

给一个主题或一条参考片，产出「拆解（可选）+ 口播稿 + 16:9 成片」。
**总控不做具体活**：它拆任务、盯状态、卡验收；写稿与出片各有专用 skill。

## 角色

| 角色 | 谁来做 | skill | 干什么 |
|---|---|---|---|
| 总控 | WorkBuddy / 任意编排 agent | `reelforge` | 拆解、组任务包、审计、验收、汇总 |
| 写稿 | 强写作模型（默认 Antigravity `gemini-4-argon-medium`，低思考） | `reelforge-writer` | `script.md` / `script.json` |
| 执行 | 编码 agent（默认 DeepSeek Harness，**官方来源** `deepseek-flash`＝V4.1 Flash，思考 max；可切 WorkBuddy 来源） | `reelforge-runner` | A/B/D 的 wvp 工程与录屏，或 C 的离线逐帧工程、音频、验收 |
| 出图 | 任意图像能力 | — | 封面、图表、插图 |

三部分通过**文件 + `state.json`** 协作；可以三个 agent 分工，也可以一个 agent 全包，只要读写同一份工作目录。
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
0.5 style      🛑 style_gate：给 2–3 个风格候选（截图/参考帧），用户选
1  reference   可选：analyze.py 拆参考 → reference.json（结构/手法/禁用）
2  script      pack_task.py writer → 写稿 agent → script.md / script.json
3  audit       similarity.py（默认40，上限60）+ 🛑 script_gate 用户确认口播稿
3.5 options    🛑 用户选：路线 A/B/C/D、配音方式/预设、字幕（模板已在 0.5 定）
3.6 fxplan     fx_pipeline.py plan → shots.json（稿子自动配动效，人只否决）
4  pilot       🛑 pilot_gate：先出 15–20 秒样片，用户看过再全篇
5  build       选路线 → A/B/D 跑 wvp，C 跑 make.py 离线逐帧（见 route-c-offline-film.md）
6  record      A=人工 OBS / record.mjs；B=EAC render-template；C=make.py+sfx.py+finalize.py 直接出片（无录屏）
7  deliver     ffprobe 验收 → 🛑 final_gate → 交付 + state done
```

五道门（`style_gate` / `script_gate` / `pilot_gate` / `audio_gate` / `final_gate`）**不能跳**；
用户明确说「不用看」才可跳过，并把原话写进 `state.json` 的 `gate_note`。
门怎么开、卡里写什么：`references/gates.md`。

### 3.6 · 稿子自动配动效（不许再问用户「这里要什么动效」）

`script_gate` 过后立刻跑，**样片必须用这套镜头表**：

```bash
python scripts/fx_pipeline.py check                      # 全库 33 个效果各渲一帧
python scripts/fx_pipeline.py plan --script work/<slug>/script.md \
       --out work/<slug>/shots.json --with-transitions --a a.mp4 --b b.mp4
python scripts/fx_pipeline.py render --shots work/<slug>/shots.json \
       --out-dir work/<slug>/clips --limit 4            # 先出 4 个片段给用户看
python scripts/fx_pipeline.py emit --shots work/<slug>/shots.json   # 可粘进 make.py
```

- `plan` 先切语义拍 → 按 `BEAT_POOL` 圈候选 → 打分 → 按配方卡的 `auto` 自动填参；
  数据类有准入门（没数据不许上图表），低置信回基础文字动效，不硬套卡。
- 用户只做**否决**：换掉某个 `fx` 或改 `params`，不许反过来让人描述动效长什么样。
- 项目侧镜头表写 `("fx", {"fx": "bar_grow", "params": {...}}, None, None, None, 1.0)`，
  `make.py` 直接调 `effects/runtime.py` 出片段。细节见 `references/effects-library.md`。

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

## 0.1 · 首次部署：先建人设（不许跳过）

第一次跑先看 `config/personas.local.yaml`；没有就让用户跑：

```bash
python scripts/personas_init.py
```

- 问用户：1 个还是多个人设；逐个问 id / 显示名 / 定位 / 口吻 / 配音方式（edge / IndexTTS 预设 / 参考干声 / 自定义）
- 汇总后**二次确认**（输入默认人设的显示名）才写本地；不确认不落盘
- 每次写稿前再问一次「这条用哪个人设」，**不要默认**——别人可能只有 1 个，也可能 3 个
- 仓库里的 ace / gatekeeper 只是示例，不要当成默认值


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

## 3.5 · 出片前四问（稿子确认后立刻问，别自己定）

> 顺序是：**先风格 → 再稿子 → 再样片 → 再全篇**。风格没定就别写稿，稿子没确认就别开工，样片没看过就别全篇。

| 问题 | 选项 | 写进 state |
|---|---|---|
| 出片路线 | A=网页章节+录屏；B=EAC film `__seek(t)`；**C=Pillow 逐帧+FFmpeg（无浏览器/EAC）**；D=wvp+EAC 混合 | `--meta render=A/B/C/D` |
| 模板/风格 | **已在 0.5 风格门定过**，这里只做复核 | `--meta template=<id>` |
| 配音 | IndexTTS 预设 / 参考干声 / edge-tts / 自定义 | `--meta tts_provider=... --meta tts_preset=...` |
| 字幕 | 烧录 / 外挂 SRT / 不要 | `--meta subs=burn/srt/none` |

问完再生成 runner 任务包：

```bash
# A / B / D：wvp 或 EAC
python scripts/pack_task.py runner --work work/<slug> --persona <id>   --render B --template motion-promo-film   --tts-provider indextts --tts-preset "<预设>" --subs burn

# C：离线逐帧（不需要浏览器、EAC、模板）
python scripts/pack_task.py runner --work work/<slug> --persona <id>   --render C   --tts-provider indextts --tts-preset "<预设>" --subs burn
```

（`\` 只是文档里的换行，实际执行时写一行。）


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
  state.json                 三部分共用状态机
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

1. **先选风格**：`style_gate` 没过，不许写稿；不许替用户默认模板。
2. **口播稿先确认**：`script_gate` 没过，不许开工。
3. **先做样片**：`pilot_gate` 没过，不许启动全篇（样片必须用最终参数，不许临时字体/配色）。
4. **参考度 ≤60**：`similarity.py` 退出码 2 就是硬失败。
5. **文案原创**：结构可借，句子不能借。
6. **五道门不跳**：每道门都要 `state.py gate` + 用户确认。
7. **执行 agent 不改稿**：要改稿回 writer，改完重新审计 + 再确认。
8. **16:9 固定**：wvp 只做 1920×1080，竖屏需求在 intake 就拒掉或换工具。
9. **不写回 skill 目录**：产物只在 `work/`。
10. **素材必须有授权字段**：`license=unknown` 的素材不能进成片。
11. **新动效必须入库且能自动被调用**：本片新写的动效，交付前登记进 `effects/index.json`
    （`entry / kind / status=ready / beats / auto / requires / pitfalls`）+ 出基准帧 +
    `fx_pipeline.py check` 全量自检；不许只留在项目目录，也不许只写文档不登记 `auto`。
12. **时间只有一个真相源**：字幕/动效/音效共用同一份句子级时间码，禁止各自按比例估算。
13. **改一处验一处**：改完抽一帧对比再说"好了"，不验像素不下结论。
14. **路线不许说错**：工程里有 `rawvideo` / `make.py` / Pillow 逐帧就是 `--render C`，不许报成 A（网页录屏）或 B（EAC film）；选完写进 state，文档与实际执行必须一致。

## 常见故障

| 现象 | 处理 |
|---|---|
| 写稿 agent 交的稿超 60% | 附 `similarity.py` 的 hint 打回，要求换结构 |
| 执行 agent 停在某阶段不动 | `state.py show` 看 stage；检查 job 状态，必要时 `continue_session` |
| dsh 没起团队 | 确认 `@nanmicoder/dsh-agent-teams` 已装，任务以 `/agent-teams ` 开头 |
| Antigravity 模型档位不对 | MCP 只认 `flash`/`flash_lite`/`pro`，要用 Argon 需改桥接 enum，见 DEPLOY.md |
| 音频和 step 对不上 | 改过 `narrations.ts` 没重跑 extract/synthesize |
| 改了参数但画面没变 | 中间产物按"文件存在"缓存了；换输入指纹或删中间产物重跑 |
| 音画整体错位 | 时间线改过但旁白没重算；校验 `abs(画面-旁白) < 0.3` |
| 多层叠图后几层不出现 | 某一路输入被裁短，`shortest` 截断了链路；输入给足整段 |
| 换 agent 后找不到效果库 | 先跑 `python scripts/effects.py where`；索引是本地+仓库合并，仓库条目优先 |
| 仓库新增效果本机看不见 | 旧脚本只认本地 `index.json`；改用 `fx_pipeline.py` / `runtime.load_index()` |
| 渲染报 `FileNotFoundError [WinError 2]` | agent 会话 PATH 没有 ffmpeg；用 `runtime.ffmpeg_bin()`，或设 `REELFORGE_FFMPEG` |
| 自动配的动效文不对题 | 检查配方卡 `beats`/`auto` 是否登记；数据类准入门会拦掉没数据的句子 |
| 文字首尾被切出画面 | 自动匹配塞了整句原文；文本效果必须走 `_fit_font` 自动缩字号 |
| 录屏没声音 | Playwright 不录系统声；用 `mix_audio.py` 拼轨后 `--audio`，或人工 OBS |
| 被问「用的 A 还是 B」答不上来 | 查工程：有 `rawvideo`/`make.py`/Pillow 就是 **C**；见 `route-c-offline-film.md` |

## 参考

| 文件 | 用途 |
|---|---|
| `references/orchestration.md` | 三部分编排、轮询、验收卡模板 |
| `references/asset-library.md` | 素材库 schema 与工作流 |
| `references/script-contract.md` | `script.json` 契约 |
| `references/wvp-handoff.md` | wvp 六阶段操作 |
| `references/tts.md` | IndexTTS 服务与 provider |
| `references/gates.md` | 五道门：时机、产物、验收卡模板 |
| `references/effects-library.md` | 效果库：配方卡契约、自动匹配、流水线接入、回归 |
| `reelforge-runner/references/route-c-offline-film.md` | **路线 C**：离线逐帧管线、命令、坑、验收（本片实战） |
| `scripts/fx_pipeline.py` | 稿子 → 镜头表 → 片段（`plan/render/emit/check/preview`） |
| `effects/runtime.py` | 项目侧渲染接缝（`render_frame` / `render_clip` / `ffmpeg_bin`） |
| `references/pitfalls.md` | 踩坑清单（硬规则，开工前必读） |
| `references/word-align.md` | 字级时间戳（可选增强）规格与接入点 |
| `references/benchmark-motion-libs.md` | 三个动效库评估：能借什么、许可红线 |
| `references/analysis.md` | 拆解口径 |
| `DEPLOY.md` / `AGENT_DEPLOY.md` | 换 agent、换模型的部署方法 |
