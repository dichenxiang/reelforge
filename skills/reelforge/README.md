# reelforge（总控）

ReelForge 的编排层：状态机、参考度审计、任务包、素材库、验收卡。
**它不写稿、不写章节代码**，只把活分给 `reelforge-writer` 和 `reelforge-runner`。

## 快速开始

```bash
python scripts/state.py init --work work/demo --title "第一条片子"
python scripts/pack_task.py writer --work work/demo --persona ace
# 把 tasks/writer.md 交给写稿 agent
python scripts/similarity.py --work work/demo --target 40 --max 60
python scripts/state.py gate --work work/demo --name script_gate
```

## 脚本

| 脚本 | 作用 |
|---|---|
| `state.py` | 三部分共用状态机（stage / status / gate / jobs） |
| `similarity.py` | 参考度审计：结构 60% + 文案 40%，上限 60 |
| `pack_task.py` | 生成 writer / runner 任务包 |
| `assets.py` | 素材库：入库、检索、投放、授权清单 |
| `make_wvp_inputs.py` | `script.json` → `script.md` / `outline.md` / `article.md` |
| `analyze.py` | 参考片拆解（转写、切点、抽帧、证据包） |
| `probe.py` | 环境自检 |
| `tts_once.py` | 单段配音 → mp3（执行侧 provider 调它） |

## 配置

- `config/pipeline.yaml`：角色、模型、参考度、画幅
- `config/personas.yaml`：账号人设与参考音频
- `config/tts.yaml`：本地 IndexTTS 服务

## 文档

- `references/orchestration.md`：三部分协作与轮询
- `references/asset-library.md`：素材库
- `references/script-contract.md`：脚本契约
- 根目录 `DEPLOY.md` / `AGENT_DEPLOY.md`：换 agent、换模型

MIT。
