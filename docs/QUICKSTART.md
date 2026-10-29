# 5 分钟快速开始

> 只想跑通第一条片子，看这一页。完整部署（含多 agent / 服务器）看 `AGENT_DEPLOY.md`。

## 你需要

| 依赖 | 版本 | 检查 |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node | 18+ | `node -v` |
| FFmpeg / ffprobe | 任意较新 | `ffmpeg -version` |
| jq | 1.6+ | `jq --version` |
| Git Bash（Windows） | — | `bash --version` |

## 四步装好

```bash
git clone <REPO_URL> reelforge && cd reelforge
bash install.sh --dsh --with-wvp        # 装到你用的 agent（--claude / --codex / --workbuddy 同理）
bash install.sh --check                 # 依赖体检：缺什么按提示补
python skills/reelforge/scripts/personas_init.py   # 建人设（1 个也可以，多轮确认才落盘）
```

Windows 没有 Git Bash？手动把 `skills/reelforge*` 复制到 agent 的 skills 目录即可。

## 第一条片子

```bash
python skills/reelforge/scripts/state.py init --work work/demo --title "第一条"
python skills/reelforge/scripts/pack_task.py writer --work work/demo
```

把 `work/demo/tasks/writer.md` 整段交给写稿 agent（Antigravity / Claude / 任意强写作模型）。
它开工前会先问：**用哪个人设 / 目标 / 受众 / 有哪些素材**。

稿子回来并确认后，定四件事：

| 选项 | 取值 | 例子 |
|---|---|---|
| 路线 | A=网页章节+录屏；B=EAC `__seek(t)` 时间轴 | A |
| 模板/风格 | `eac_probe.py` 列出的 id；没有 EAC 就不填 | `motion-promo-film` |
| 配音 | IndexTTS 预设 / 参考干声 / edge-tts / 自定义 | `indextts` + `有感情青年音` |
| 字幕 | 烧录 / 外挂 SRT / 不要 | 烧录 |

```bash
python skills/reelforge/scripts/pack_task.py runner --work work/demo \
  --render A --template <id> --tts-provider indextts --tts-preset "<预设>" --subs burn
```

把 `work/demo/tasks/runner.md` 交给执行 agent。

## 产物

```
work/demo/
  script.md / script.json / outline.md   # 稿子
  presentation/                          # 工程（路线 A）
  out/final.mp4 / final.srt              # 成片 + 字幕
  state.json                             # 状态与门
```

## 没有 GPU 怎么办

用 edge-tts：

```bash
python -m pip install edge-tts
python skills/reelforge/scripts/tts_once.py --text "测试" --out /tmp/probe.mp3 --provider edge --persona host
```

## 卡住了

- 依赖/环境：`python skills/reelforge-runner/scripts/preflight.py`
- 路由/模板：`python skills/reelforge-runner/scripts/eac_probe.py`
- 常见错误：`AGENT_DEPLOY.md` §9
- 开源审计与待办：`docs/OPEN-SOURCE-AUDIT.md`
