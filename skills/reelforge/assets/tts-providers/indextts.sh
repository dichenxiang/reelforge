#!/usr/bin/env bash
# wvp 的 TTS provider：本地 IndexTTS（video-factory 自带）
# 用法：复制到 <project>/scripts/tts-providers/indextts.sh
#       PRESENTATION_TTS=indextts npm run synthesize-audio

VF="${VIDEO_FACTORY_DIR:-C:/Users/dichengxiang/.workbuddy/skills/video-factory}"
PY="${VIDEO_FACTORY_PY:-python}"

tts_synthesize() {
  local text="$1" out="$2" voice="${3:-}"
  local args=(--text "$text" --out "$out")
  [ -n "${TTS_PERSONA:-}" ] && args+=(--persona "$TTS_PERSONA")
  if [ -n "${TTS_REF_AUDIO:-}" ]; then
    args+=(--ref-audio "$TTS_REF_AUDIO")
  elif [ -n "$voice" ] && [ -f "$voice" ]; then
    args+=(--ref-audio "$voice")
  fi
  "$PY" "$VF/scripts/tts_once.py" "${args[@]}"
}

tts_check() {
  [ -f "$VF/scripts/tts_once.py" ] || return 1
  "$PY" -c "import sys" >/dev/null 2>&1
}

tts_install_help() {
  cat >&2 <<'HELP'
IndexTTS provider 需要：
  1) PATH 里有 python
  2) D:/indexTTS/extracted/IndexTTS2.0_v3（服务没起会自动拉起，约 40 秒加载）
  3) 参考音频：config/personas.yaml 的 voice.ref_audio
可用环境变量覆盖：VIDEO_FACTORY_DIR / TTS_PERSONA / TTS_REF_AUDIO
HELP
}
