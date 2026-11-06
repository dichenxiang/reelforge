# ReelForge 跨 Agent 路由（换 agent 不丢库）

> 给任何 agent 看的唯一入口。做视频 / 配动效之前先读本文件，不要凭记忆找路径。

## 1. 统一效果库（唯一真相源）

| 项 | 路径 |
|---|---|
| 效果库本体 | `~/.reelforge/effects`（可用 `REELFORGE_EFFECTS` 覆盖） |
| 素材库 | `~/.reelforge/library`（可用 `REELFORGE_LIBRARY` 覆盖） |
| 索引 | 本地 `index.json` + 随仓库分发的 `effects/index.json` **合并，仓库条目优先** |
| 配方卡目录 | `catalog/`（232 张，随仓库分发） |

**本机效果库为空也能出片**：`runtime.resolve_entry()` 会回退到随 skill 分发的 `effects/fx/*.py`。
所以「换 agent 找不到库」不是拒绝理由，先跑第 3 节的 `check`。

## 2. 六个技能目录（内容完全相同，选当前 agent 那个）

| agent | 总控技能目录 `<RF>` |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/reelforge` |
| Codex CLI | `~/.codex/skills/reelforge` |
| Claude Code | `~/.claude/skills/reelforge` |
| Gemini CLI | `~/.gemini/skills/reelforge` |
| **Antigravity** | **`~/.gemini/antigravity/skills/reelforge`** |
| **DeepSeek Harness** | **`~/.dsh/skills/reelforge`** |

> ⚠️ Antigravity **不是** `~/.claude/skills`，也不等于 Gemini CLI 的 `~/.gemini/skills`；它有自己的 `~/.gemini/antigravity/skills`。DSH 同理。这两个最容易漏同步，验的时候必须单独查。

五个技能一起分发：`reelforge`（总控 / 效果库所在）、`reelforge-writer`、`reelforge-runner`、`reelforge-duo`、`reelforge-router`。
**注意：`effects.py` / `fx_pipeline.py` / `effects/` 只在总控 `reelforge` 目录里**，runner / writer / duo 目录没有，别在那里找。
同步后用 `bash install.sh --all` 可一次覆盖六个目标（先备份再覆盖式更新，不删目录）；只改文档时可只同步各目录的 `SKILL.md`。

## 3. 四条命令（一律用绝对路径）

```bash
RF=~/.codex/skills/reelforge                     # 换成上表对应目录
python "$RF/scripts/fx_pipeline.py" check       # 33 个效果各渲一帧
python "$RF/scripts/fx_pipeline.py" plan --script script.md --out shots.json --with-transitions
python "$RF/scripts/fx_pipeline.py" render --shots shots.json --out-dir clips --fps 24
python "$RF/scripts/fx_pipeline.py" emit --shots shots.json          # 生成 make.py 镜头表
python "$RF/scripts/effects.py" where                                # 统一库绝对路径
python "$RF/scripts/effects.py" list                                 # 列效果与状态
```

项目侧接缝：`effects/runtime.py` 的 `render_frame()` / `render_clip()`；镜头表可写
`{"fx": "bar_grow", "params": {...}}`，`make.py` 的 `("fx", {...})` 分支直接调用。

## 4. 环境兜底

- ffmpeg 不在 agent 的 PATH：`runtime.ffmpeg_bin()` 自动找 `~/.local/bin/ffmpeg.exe`，或设 `REELFORGE_FFMPEG=<绝对路径>`。
- 渲染报 `FileNotFoundError [WinError 2]` → 是 ffmpeg 找不到，不是效果库丢了。
- 仓库新增效果本机看不见 → 别用旧脚本读本地 `index.json`，用 `fx_pipeline.py` / `runtime.load_index()` 的合并索引。

## 5. 契约

- 33 个可运行动效、9 个待抽取老镜头、232 张配方卡（选型参考）。
- 新动效必须 `register` + `baseline` + 写 `auto` 配方，否则自动匹配选不中。
- `plan` 按语义节拍匹配，数据句没有数字不上图表，低置信退回基础文字动效。
- 完整契约见 `<RF>/references/effects-library.md`。

## 6. 一键校验（别凭"我复制过了"下结论）

```bash
python tests/verify_agents.py            # 六个目录关键文件哈希一致性
python tests/verify_agents.py --smoke    # 额外逐个在空本地库 + 独立 cwd 下渲一个 mp4
```

任一目录缺失 / 版本不一致 / 冒烟失败，退出码非 0。这个校验就是「换 agent 不丢库」的回归测试，改完效果库或同步完必须跑。

## 7. 出片路线统一编号（选完写进 state，别混着说）

| 路线 | 做法 | 前提 |
|---|---|---|
| A | wvp 网页章节 + `record_auto.mjs` / OBS 录屏 | 浏览器 + wvp vendor |
| B | EAC film，整片一个 `__seek(t)` 的 `film.html` | EAC design world 插件 |
| **C** | **Pillow 离线逐帧 → `rawvideo` → FFmpeg 编码 → 拼段混音（无录屏）** | Python + Pillow + FFmpeg |
| D | wvp 主体 + EAC 风格层 + 少量库动效（A 的增强） | A 工程 + EAC 模板 |

`--meta render=A/B/C/D`；路线 C 契约见 `reelforge-runner/references/route-c-offline-film.md`，B 见 `route-b-eac-film.md`，D 见 `eac-bridge.md`。
**不许把 C 说成 A 或 B**：工程里有 `make.py` / `rawvideo` / Pillow 逐帧就是 C。旧版 `eac-bridge.md` 曾把「混合」叫 C，现已统一改为 D。

GitHub：`https://github.com/dichenxiang/reelforge`（`skills/` 为分发源）。
