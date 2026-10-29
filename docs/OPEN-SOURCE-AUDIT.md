# 开源前通用化审计 · ReelForge v0.1

> 审计对象：`D:\reelforge-repo`（157 个文件，核心 4 个 skill + 2 个 MCP + 安装器）
> 结论一句话：**流水线本身是可复用的，但仓库现在仍是“作者本机工作台”** —— 个人路径、
> 个人人设、单一 TTS、单一 agent、Windows 假设、第三方素材许可都没有收口。
> 开源前需要做一次“核心 ↔ 适配器”的拆分，而不是补几行 README。

---

## 0. 已经是通用资产、应当保留的部分

| 模块 | 文件 | 为什么值得留 |
|---|---|---|
| 四道门状态机 | `skills/reelforge/scripts/state.py`、`pack_task.py`、`similarity.py` | 状态/门/参考度审计与具体模型无关，是流程骨架 |
| 逐拍旁白 + 时间轴混音 | `mix_audio.py`、录制/混音链路 | 把“每拍音频”变成成片音轨，是这类视频的核心难点 |
| 参考度/相似度审计 | `similarity.py` | 开源项目里少见的“防抄参考片”约束 |
| EAC 桥（本次新增） | `reelforge-runner/scripts/eac_probe.py`、`references/eac-bridge.md` | 只读探测，不绑定插件会话 |
| 文档分层 | `README / DEPLOY / AGENT_DEPLOY` | 人读 / 部署 / agent 读三份，结构对 |

---

## 1. P0：不修不能公开

| # | 问题 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| P0-1 | 个人配置会被误提交 | `git status` 里 `skills/reelforge/config/personas.local.yaml` 为未跟踪；`.gitignore` 只忽略 `personas.yaml` | 泄露本机路径、人设、私有音色配置 | 已补 ignore；仓库只留 `*.example.yaml`，运行时 `cp` 生成 local |
| P0-2 | TTS provider 写死作者路径 | `skills/reelforge/assets/tts-providers/indextts.sh:6`：`VF="${VIDEO_FACTORY_DIR:-C:/Users/dichengxiang/.workbuddy/skills/video-factory}"` | 别人一跑就 `tts_once.py not found` | 改成必填 env（或从 skill 自身路径推导），缺失时给一行安装说明 |
| P0-3 | `mcp/antigravity` 是个人自动化 + 抓取器 | `douyin_cdp.py` 直连抖音抓流、`CHROME` 硬编码 `C:\Program Files\Google\Chrome\...`；`server.py` 硬编码多条 ffmpeg 路径 | 平台 ToS / 版权争议；换机器不可用 | 拆到 `adapters/optional/`，默认不安装；抓取器单独仓库或明确“仅个人研究，不随主仓库” |
| P0-4 | `mcp/deepseek-harness` 绑定本机安装 | `server.py` 写死 `D:\Deepseek Herness\...`、`C:\Program Files\DeepSeek Harness\...` | 非本机用户无法启动 | 改为 `DSH_HOME` / `which` 探测 + 配置项 |
| P0-5 | 安装器只有 bash，且不检查依赖 | `install.sh` 用 `cp -R`、`date`、`USERPROFILE`；没有 python/node/jq/ffmpeg/playwright 检查 | Windows 无 Git Bash 直接失败；缺依赖到第 4 步才炸 | 写 `install.py`（跨平台）或 `install.sh + preflight.py`；README 写清“Windows 需 Git Bash” |
| P0-6 | 许可没有收口 | README 只写 MIT；`vendor/` 被 ignore 但依赖 wvp(MIT)、动效库(Apache-2.0)、onetake(PolyForm NC)、字体(OFL) 都没清单 | 开源后被指出“许可不明”，商用用户踩 NC 条款 | 已加 `THIRD_PARTY_NOTICES.md`；README 增加“不随仓库分发”的说明与成片署名规则 |
| P0-7 | 示例/状态文件含绝对路径 | `state.json`、`DELIVERY.md`、示例 `work/` 里全是 `D:\视频\...` | 暴露目录结构/用户名 | 文档示例用 `<work>`；`work/` 已 ignore，但示例目录需脱敏 |

---

## 2. P1：决定“别人能不能真的用起来”

### 2.1 平台假设（Windows 中心）

- **SAPI 兜底**：`tts.py`/`tts_once.py` 的 Windows 分支、`voice.ps1`；macOS/Linux 没有等价路径。
- **Edge 路径**：wvp 模板 `render.js` 硬编码 `C:/Program Files (x86)/Microsoft/Edge/...`；macOS 需 Channel 或 chromium。
- **PowerShell**：安装/探测脚本多处 `powershell -Command`。
- **剪映导出**：`eac_job_submit type=export` 的草稿目录是 Windows 路径。

> 建议：抽 `platform.py`（`IS_WIN/IS_MAC`、`find_app("edge")`、`tts_engine()`），所有硬编码路径走
> “env → which → 常见安装位置”三级探测；文档给 macOS/Linux 的“纯 wvp + edge-tts”最小路径。

### 2.2 TTS 只有 IndexTTS 一条路

- 当前 `tts.py` 的 provider 只有 `http`（IndexTTS）和 `edge`，且 `indextts.sh` 绑定作者目录。
- 建议定义 provider 契约（`tts_synthesize(text,out,voice)`），内置：
  `edge`（零依赖、跨平台、GPL 边界要声明）→ `indextts`（本地克隆，推荐）→ `openai`（兼容接口）→ `custom-http`。
- `probe.py` 输出“当前可用音色/服务状态/预估 RTF”，让用户一眼知道走哪条。

### 2.3 与人设/品牌耦合

- `personas.example.yaml` 里是“阿测 / 把关学长”，禁词表、口头禅、配色都是作者品牌。
- 建议：默认 `host`（中性主讲人），把两套人设移到 `examples/personas/`；禁词表做成配置项，
  不要把“全网最强/必买”等规则写死在代码里。

### 2.4 与具体 agent 耦合

- 文档默认 Antigravity 写稿 + WorkBuddy 总控 + DSH 执行；`mcp/` 只服务这三家。
- 建议：定义 **Writer 契约**（输入：主题/链接/人设/预算；输出：`source_digest.md`/`script.md`/
  `script.json`/`writer-notes.md`）与 **Runner 契约**（输入：outline/script/assets；输出：成片+SRT）。
  任意模型只要能读写文件就能接；`install.sh` 的 `--antigravity` 只是其中一种预设。

### 2.5 录屏/混音链路没有下沉

- 本次真正通用的 `record-auto.mjs`（同步白块 + step 时间戳采样）与 `mix_final.py`
  （按 timeline 混音、裁同步块、25→30fps）现在只在**示例工程**里。
- 建议移到 `reelforge-runner/scripts/`，参数化：`--url/--steps/--trail/--size/--fps`；
  并把“用 `vite preview` 而不是 dev server 录屏”写成默认（Vite 原子写会命中旧模块缓存，本次已踩）。

### 2.6 渲染后端二选一没有接口

- wvp（React 章节 + 逐拍音频）与 EAC film（`__seek(t)` 逐帧）是两条完全不同的管线。
- 建议定义 `render_backend`：`build(work) -> web_root`、`capture(web_root) -> video`、`mix(video, audio) -> mp4`；
  wvp/EAC 各自实现，交付物不变（MP4+SRT+工程）。

### 2.7 文档与版本

- 只有中文；缺 5 分钟 quickstart、失败排查表、术语表（trio/duo/gate/wvp）。
- `npm create vite@latest`、`playwright`、`vite` 都没锁版本 → 半年后别人跑不起来。
- 建议：英文 README（可机翻后人工过一遍）、`docs/QUICKSTART.md`、`docs/FAQ.md`、`requirements.txt`/`package-lock`。

---

## 3. P2：工程化与质量

| 项 | 现状 | 建议 |
|---|---|---|
| 测试 | 0 个测试 | `pytest` 覆盖 state/pack_task/similarity/SRT/mix 的纯函数；录屏链路做 15s 假章节 e2e |
| CI | 无 | GitHub Actions：ubuntu + windows，无 GPU；TTS 用 mock，只验证构建/录屏/混音 |
| 代码质量 | 无 lint | `ruff`（py）+ `oxlint`（前端）+ pre-commit |
| 编码 | 控制台 GBK 导致中文乱码（本次多次出现） | 脚本统一 `sys.stdout.reconfigure(encoding="utf-8")`；README 提示 `PYTHONIOENCODING=utf-8` |
| 进程 | `duo.py` 用 `subprocess(capture_output=True)`，部分沙箱（DSH）直接 `WinError 5` | 改为临时文件重定向或 `--no-pipe`；错误信息给替代命令 |
| 安全 | MCP server 监听本机但无鉴权；路径校验弱 | 只绑 `127.0.0.1`、校验路径前缀、日志不打印正文 |
| 仓库卫生 | `__pycache__`、`.lock`、示例产物 | 已补 ignore；加 `.gitattributes`（LF）与 `pre-commit` |

---

## 4. 建议的仓库结构（v0.2）

```
reelforge/
  core/                 # 与模型/平台无关：state, pack_task, similarity, srt, timeline
  adapters/
    tts/                # edge / indextts / openai / custom-http
    render/             # wvp / eac-film
    agents/             # writer/executor 的 prompt 包与 MCP 桥（optional）
    platform/           # 路径、浏览器、ffmpeg 探测
  skills/               # 给 agent 读的 SKILL.md（薄，指到 core/adapters）
  examples/             # 60s 最小示例 + 人设示例 + 参考片拆解
  docs/                 # QUICKSTART / FAQ / GLOSSARY / ARCHITECTURE
  tests/                # pytest + e2e
  install.py            # 跨平台安装 + preflight
  THIRD_PARTY_NOTICES.md
```

原则：**skill 只写“怎么判断/怎么验收”，代码进 core/adapters；平台差异进 adapters/platform；
示例进 examples。** 现在 skill 里混了太多“作者机器的现实”。

---

## 5. 分阶段计划

| 版本 | 范围 | 验收 |
|---|---|---|
| **v0.2 可移植核心**（约 3–5 天） | 拆 core/adapters；install.py + preflight；TTS 三 provider；录制/混音下沉；THIRD_PARTY_NOTICES；英文 README | 全新 Windows 与 macOS 空机器，各跑通一条 30s 无 GPU（edge-tts）片 |
| **v0.3 适配器与示例**（约 1 周） | EAC 可选适配器；agent 契约与单 agent 模式；2 个示例（口播片/无旁白片）；CI | 示例在 CI 上构建 + 录 15s 片段通过 |
| **v1.0 发布** | 文档站、版本 pin、发布脚本、贡献指南、Issue 模板 | 外部贡献者按 QUICKSTART 30 分钟内出片 |

---

## 6. 本次已顺手修掉的（零风险）

- `.gitignore` 补：`personas.local.yaml`、`.dsh-ops-update-*.lock`、`node_modules/`、`dist/`、`.venv/`
- 删除仓库里残留的两个 `.lock` 空文件
- 新增 `THIRD_PARTY_NOTICES.md`（许可模板 + 成片署名建议）
- （上一轮）`reelforge-runner` 增加 P0.5 EAC 桥：`references/eac-bridge.md` + `scripts/eac_probe.py`

## 7. 下一步建议先做哪一个

如果只做一件事：**把 `record-auto.mjs` + `mix_final.py` 下沉并参数化**。
它是这条流水线里最不可替代、也最容易复用的 200 行；其他都可以慢慢补文档。
