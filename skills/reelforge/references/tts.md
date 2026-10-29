# 旁白（TTS）

主流程按 **wvp 的 step 颗粒度**合成：每个 step 一个 mp3，落在
`presentation/public/audio/<chapter>/<step>.mp3`，`?auto=1` 录屏时自动播。

## 主流程：IndexTTS（本地克隆音色）

前提：`script.md` / `outline.md` 已定稿，章节的 `narrations.ts` 写完。

```bash
cd work/<slug>/presentation
npm run extract-narrations        # narrations.ts → audio-segments.json
PRESENTATION_TTS=indextts TTS_PERSONA=ace npm run synthesize-audio
```

- provider 文件：`assets/tts-providers/indextts.sh`，建工程时复制到
  `<project>/scripts/tts-providers/`。
- 它内部调 `scripts/tts_once.py`，走本地 IndexTTS 服务（`http://127.0.0.1:7860`）。
- 服务没起会自动拉起，约 40 秒加载；之后每段 2–5 秒。
- 换人设：`TTS_PERSONA=gatekeeper`；换参考音频：`TTS_REF_AUDIO=D:/x.wav`。
- 增量：已存在的 mp3 会跳过；要全部重来加 `-- --force`，或删 `public/audio/<id>/`。

服务管理：

```bash
# 常驻（推荐，批量做片时不用反复加载）
D:/indexTTS/extracted/IndexTTS2.0_v3/start_server.bat
# 日志（自动拉起时）
%TEMP%\vf-tts-server.log
```

## 备用：逐拍合成（tts.py）

不走 wvp、或者要先把旁白单独做出来听时用：

```bash
python scripts/tts.py --work work/<slug> --persona ace                   # provider 取人设，默认 http
python scripts/tts.py --work work/<slug> --persona ace --provider edge    # 没显卡时回退
```

输出 `<work>/showreel/audio/beat_XX.wav` + `narration.wav` + `narration.json`，
仅作为素材，不再进 wvp 的自动播放链路。

## 服务与显存

- IndexTTS 2.0 打包版在 `D:/indexTTS/extracted/IndexTTS2.0_v3`，8GB 卡加载后约 7GB。
- 参考音频：`D:/indexTTS/voices/ace_ref.wav`、`gate_ref.wav`（10–13 秒）。
  换成自己的干声效果最好，路径写进 `config/personas.yaml` 的 `voice.ref_audio`。
- 不要同时开游戏或第二个模型，否则显存换页，速度掉到 1/30。

## 时长对不上怎么办

`narrations.ts` 定稿后先 extract 再合成，实际音频时长会和 outline 的估算有偏差：

- 单段超 6 秒：这句话该拆成两个 step（内容太多）
- 单段不足 1.2 秒：信息太薄，合并或补一句
- 整片偏差 >10%：回 `outline.md` 调 step 数，再重跑 extract + synthesize

**不要**用变速来对齐，声音会失真。
