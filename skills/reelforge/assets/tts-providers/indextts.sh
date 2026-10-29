#!/usr/bin/env bash
# wvp 的 TTS provider：本地 IndexTTS（克隆音色 / 预设音色）
# 用法：复制到 <project>/scripts/tts-providers/indextts.sh
#       PRESENTATION_TTS=indextts TTS_PERSONA=host TTS_PRESET="有感情青年音" npm run synthesize-audio
#
# 查找顺序（第一个存在即用）：
#   1) $VIDEO_FACTORY_DIR/scripts/tts_once.py
#   2) $REELFORGE_HOME/scripts/tts_once.py
#   3) ~/.dsh/skills/reelforge/scripts/tts_once.py
#   4) ~/.workbuddy/skills/reelforge/scripts/tts_once.py
#   5) ~/.claude/skills/reelforge/scripts/tts_once.py
#   6) ~/.codex/skills/reelforge/scripts/tts_once.py

PY="${VIDEO_FACTORY_PY:-python}"

find_vf() {
  local c
  for c in \
    "${VIDEO_FACTORY_DIR:-}" \
    "${REELFORGE_HOME:-}" \
    "$HOME/.dsh/skills/reelforge" \
    "$HOME/.workbuddy/skills/reelforge" \
    "$HOME/.claude/skills/reelforge" \
    "$HOME/.codex/skills/reelforge" \
    "$HOME/.gemini/antigravity/skills/reelforge"
  do
    [ -n "$c" ] && [ -f "$c/scripts/tts_once.py" ] && { echo "$c"; return 0; }
  done
  return 1
}

VF="$(find_vf || true)"
if [ -z "$VF" ]; then
  echo "[indextts] 找不到 reelforge/scripts/tts_once.py" >&2
  echo "          设 VIDEO_FACTORY_DIR 指向 reelforge skill，或先跑 install.sh --dsh" >&2
  exit 1
fi

tts_synthesize() {
  local text="$1" out="$2" voice="${3:-}"
  local args=(--text "$text" --out "$out")
  [ -n "${TTS_PERSONA:-}" ] && args+=(--persona "$TTS_PERSONA")
  [ -n "${TTS_PRESET:-}" ] && args+=(--preset "$TTS_PRESET")
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
  2) 本机 IndexTTS 2.0 服务（默认 http://127.0.0.1:7860；没起会按 config/tts.yaml 自动拉起）
  3) 参考音频（personas 里的 voice.ref_audio）或预设名（TTS_PRESET）
可用环境变量：VIDEO_FACTORY_DIR / REELFORGE_HOME / TTS_PERSONA / TTS_PRESET / TTS_REF_AUDIO
列预设：python <reelforge>/scripts/tts_once.py --list-presets --out /tmp/x.mp3
HELP
}
