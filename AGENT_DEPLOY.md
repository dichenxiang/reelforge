# AGENT_DEPLOY.md — 给 AI 的自部署指令（v0.2）

> **用户只需要做一件事**：把仓库地址发给你，加一句
> 「读 `AGENT_DEPLOY.md`，按步骤部署，缺什么自己装，要拍板的问我」。
>
> 你是执行部署的 agent。目标：**装好 skill → 依赖体检全绿 → 生成本地人设 → 跑通一条 30 秒验证片**。
> 不要编造成功；每一项都要有命令输出或文件作为证据。

---

## 0. 你的输入

| 输入 | 必需 | 说明 |
|---|---|---|
| 仓库地址 | 是 | `https://github.com/<owner>/reelforge.git`（或本地路径） |
| 目标 agent | 否 | 不提供就按 §1 自动探测 |
| 模式 | 否 | `trio`（无人值守）/ `duo`（人在电脑前）；默认 trio |
| 人设信息 | **是** | 见 §2 问卷，一次问完 |
| 配音条件 | 否 | 有 IndexTTS 就克隆，没有就 edge-tts |
| EAC 剪辑插件 | 否 | 装了才支持路线 B（`__seek(t)` 成片） |

---

## 1. 克隆 + 探测（只读，先做）

```bash
git clone <REPO_URL> reelforge
cd reelforge
REPO="$(pwd)"                        # 后面所有命令都用 $REPO
uname -s 2>/dev/null || ver          # Windows 用 Git Bash
python --version; node -v; npm -v; jq --version; ffmpeg -version | head -1; git --version
```

探测用户装了哪些 agent（存在哪个目录就装哪个）：

| 目录 | agent | 装什么 |
|---|---|---|
| `~/.dsh/skills` | DeepSeek Harness | 总控 + 执行 + duo |
| `~/.claude/skills` | Claude Code | 全部 |
| `~/.codex/skills` | Codex CLI | 全部 |
| `~/.workbuddy/skills` | WorkBuddy | 全部 |
| `~/.gemini/antigravity/skills` | Antigravity | 写稿 |

一个都没有 → 问用户用哪个；仍没有 → 按 §3 的“无 skills 机制”降级（写进 `AGENTS.md`）。

---

## 2. 只问一次：用户问卷（复制给用户填）

```
部署 ReelForge 需要你定 5 件事（一次答完，后面不再问）：

1) 装给哪个 agent？（检测到：<列表>；默认全装）
2) 几个口播人设？（1 个也可以；多个人设请逐个给：名字 / 定位一句话 / 说话风格 / 禁词）
3) 配音用哪种？
   a. 本地 IndexTTS（有 GPU / 已装）——可列预设让你选
   b. edge-tts（免费、无需 GPU）
   c. 我自己的 10–20 秒干声（给路径）
   d. 自定义命令（接 OpenAI 兼容 / ElevenLabs 等）
4) 装没装 EAC design world 剪辑插件？（有 → 可选路线 B：motion-promo-film 时间轴）
5) 用 trio（无人值守）还是 duo（你在电脑前拍板）？
```

**用户没答的**：人设用通用 `host`（主讲人），配音走 edge-tts（没装就提示装），EAC 视为没有，模式 trio。
把这些“缺省”写进最终报告，不要静默。

---

## 3. 装 skill

```bash
cd reelforge
bash install.sh --dsh --claude --codex --workbuddy --antigravity --with-wvp
# 只装探测到的：按需删参数；--with-wvp 拉 web-video-presentation
```

- Windows 必须用 **Git Bash**（`bash install.sh ...`）；没有 Git Bash 就按 §1 表格手动 `cp -R skills/<name>`。
- 装完会打印**依赖体检**；不通过先按提示补，别往下走。
- 没有 skills 机制的 agent：把 `skills/reelforge*/SKILL.md` 的要点追加到项目 `AGENTS.md`，脚本仍可调用。

> 离线/克隆失败：下载 zip 解压后用同样目录；wvp 拉不下来时先跳过，路线 A 会提示缺 vendor。

---

## 4. 装运行依赖

```bash
python -m pip install -r requirements.txt          # numpy / pyyaml / Pillow
python -m pip install edge-tts                     # 可选：无 GPU 的旁白兜底
```

系统依赖：`ffmpeg`、`ffprobe`、`jq`、`node>=18`。

| OS | 命令 |
|---|---|
| Windows | `winget install Gyan.FFmpeg jqlang.jq OpenJS.NodeJS` |
| macOS | `brew install ffmpeg jq node` |
| Ubuntu | `sudo apt install ffmpeg jq nodejs npm` |

没有 sudo / 装不了 → 停下告诉用户缺什么，**不要改系统源**。
录屏用 `playwright-core`（装在**工程目录**，不要全局）：
```bash
cd <你的 presentation 工程> && npm i -D playwright-core
```
脚本会先按自身目录、再按当前目录找它；浏览器优先用本机 Edge，没有就 `npx playwright install chromium`。

---

## 5. 生成本地人设（必须走脚本，不要手写半成品）

先按 §2 答案生成 `/tmp/personas.json`：

```json
{
  "version": 1,
  "default_persona": "host",
  "personas": [
    {
      "id": "host",
      "display_name": "主讲人",
      "positioning": "把复杂东西讲清楚的过来人",
      "personality": ["直接", "先给结论"],
      "banned": ["全网最强", "必买"],
      "voice": {"provider": "edge", "voice": "zh-CN-YunxiNeural", "rate": "+0%"},
      "prompt_block": "你是「主讲人」，先给结论再拆依据，短句口语，不编。"
    }
  ]
}
```

```bash
python skills/reelforge/scripts/personas_init.py --from-json /tmp/personas.json --yes
python skills/reelforge/scripts/personas.py --list        # 应列出人设
```

多人设就多写几个对象，`default_persona` 指向默认那个。
**不要预设“阿测 / 把关学长”**，那是示例。

---

## 6. 配音（按用户选择）

### 6.1 IndexTTS（推荐，有 GPU）

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7860/   # 200 = 服务在
python skills/reelforge/scripts/tts_once.py --list-presets --out /tmp/probe.mp3
# 让用户选预设，然后冒烟：
python skills/reelforge/scripts/tts_once.py --text "这是一条旁白测试" --out /tmp/probe.mp3 --preset "<预设>"
```

写进 persona 的 `voice.preset`，或运行时用 `TTS_PRESET`。

### 6.2 edge-tts（无 GPU）

```bash
python -m edge_tts --list-voices | grep zh-CN
python skills/reelforge/scripts/tts_once.py --text "这是一条旁白测试" --out /tmp/probe.mp3 --persona host --provider edge
```

### 6.3 用户干声

要 10–20 秒、无背景音；写进 `voice.ref_audio`（绝对路径）。

**任何情况下都不要用 Windows SAPI**（Huihui/KangKang/Yaoyao），机械音。

---

## 7. 出片路线与模板（装了 EAC 才有得选）

```bash
python skills/reelforge-runner/scripts/eac_probe.py --json > /tmp/eac-pack.json
```

- 有 EAC：把模板列表给用户选（默认 `motion-promo-film`），路线 A/B 二选一；
  路线 B 细节见 `skills/reelforge-runner/references/route-b-eac-film.md`。
- 没有 EAC：只支持路线 A，**不要声称支持 B**。

记录到项目状态：`state.py set --work <work> --meta render=A --meta template=<id>`。

---

## 8. 校验（全部要过，逐条给输出）

```bash
python skills/reelforge-runner/scripts/preflight.py
bash skills/reelforge/vendor/web-video-presentation/scripts/scaffold.sh --list-themes | head
python skills/reelforge/scripts/state.py init --work /tmp/rf-smoke --force
python skills/reelforge/scripts/pack_task.py writer --work /tmp/rf-smoke   # 应含“开工前先问清楚”
ls -la /tmp/probe.mp3
```

再跑一条**真录 5 秒**（验证浏览器 + 录屏链路，不依赖 wvp、不需要起服务器）：

```bash
mkdir -p /tmp/rf-web && cd /tmp/rf-web
printf '<!doctype html><meta charset="utf-8"><body style="background:#0a0d16;color:#dfff43;font:48px sans-serif;display:grid;place-items:center;height:100vh">ReelForge smoke</body>' > index.html
cd /tmp/rf-web && npm init -y >/dev/null 2>&1 && npm i -D playwright-core >/dev/null 2>&1
URL=$(python -c "from pathlib import Path; print(Path('index.html').resolve().as_uri())")
node "$REPO/skills/reelforge-runner/scripts/record_auto.mjs" --url "$URL" --duration 5 --out /tmp/rf-rec.webm --no-marker
ls -la /tmp/rf-rec.webm
```

期望：preflight 硬依赖全绿；scaffold ≥10 个主题；writer 任务包含“开工前先问”；probe.mp3 存在；
`/tmp/rf-rec.webm` > 0 字节。

---

## 9. 常见失败

| 现象 | 处理 |
|---|---|
| `install.sh` 报 `ensure_config: command not found` | 旧版本 bug，升级到本仓库最新 `install.sh` |
| `jq: command not found` | 装 jq；`synthesize-audio` 依赖它 |
| `tts_once` 连不上 7860 | 起 IndexTTS 服务，或改 `config/tts.yaml` 的 `start_cmd`；无 GPU 改 edge-tts |
| `playwright ... Executable doesn't exist` | `npx playwright install chromium`，或让 `record_auto.mjs` 用本机 Edge（默认） |
| `No such file: vendor/web-video-presentation` | `bash install.sh --with-wvp`（失败用 zip，见 §3） |
| 中文乱码 | 终端改 UTF-8，或设 `PYTHONIOENCODING=utf-8` |
| 录屏是旧章节 | 用 `vite preview` 的生产构建录，不要用 dev server |
| `python -m http.server` 报 `WinError 10013` | Windows 端口被占/保留；改用 `file://` 页面或换端口 |

---

## 10. 汇报模板（发给用户）

```
ReelForge 部署完成
环境：<OS> · python <v> · node <v> · jq <v> · ffmpeg <v>
agent：<已装目录列表>
skill：总控 <path> · 写稿 <path> · 执行 <path> · duo <是/否>
wvp：<路径/主题数>
人设：<id/显示名/数量>（默认 <id>）
配音：<provider + preset/音色>；试听 /tmp/probe.mp3
路线：<A/B>；模板：<id 或 无>
校验：preflight <ok> · scaffold <ok> · writer 任务 <ok> · 5s 录屏 <ok>
待用户补：<无 / 具体项>
第一条片子：
  python skills/reelforge/scripts/state.py init --work work/demo --title "第一条"
  python skills/reelforge/scripts/pack_task.py writer --work work/demo
```

---

## 11. 红线

- 不提交密钥/token/cookie；不把用户私有素材传到外网。
- 不覆盖用户已有配置（先备份）；不改 `vendor/` 上游代码。
- 没跑完 §8 不说“部署完成”；做不到的项明确写“未完成 + 原因 + 下一条命令”。
