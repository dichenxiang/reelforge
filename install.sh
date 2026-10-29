#!/usr/bin/env bash
# ReelForge 安装脚本
#
#   bash install.sh --workbuddy --antigravity --dsh
#   bash install.sh --all
#   bash install.sh --with-wvp
#
# 只会复制 skill、生成配置、拉 wvp；不会装系统软件、不会碰你的密钥。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Git Bash 的 $HOME 有时被改到 AppData，Windows 上优先用 USERPROFILE
UHOME="${REELFORGE_USER_HOME:-${USERPROFILE:-$HOME}}"
CFG="$REPO/skills/reelforge/config"
FORCE=0
CHECK_ONLY=0
WITH_WVP=0
WITH_HUMANIZER=0
TARGETS=()

usage() {
  sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

目标（可多选）：
  --workbuddy     ~/.workbuddy/skills       （总控 + 写稿 + 执行）
  --antigravity   ~/.gemini/antigravity/skills （写稿）
  --dsh           ~/.dsh/skills             （执行）
  --claude        ~/.claude/skills          （三个都装）
  --codex         ~/.codex/skills           （三个都装）
  --all           以上全部

其它：
  --with-wvp      稀疏克隆 web-video-presentation 到 skills/reelforge/vendor
  --with-humanizer  装 humanizer-zh（去 AI 味清洗）到 workbuddy / antigravity / codex
  --force         覆盖已存在的同名 skill（默认先备份为 *.bak-日期）
  --check         只做依赖体检（python/node/ffmpeg/jq/wvp/TTS），不安装
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workbuddy|--antigravity|--dsh|--claude|--codex) TARGETS+=("${1#--}") ;;
    --all) TARGETS=(workbuddy antigravity dsh claude codex) ;;
    --with-wvp) WITH_WVP=1 ;;
    --with-humanizer) WITH_HUMANIZER=1 ;;
    --check) CHECK_ONLY=1 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1"; usage; exit 1 ;;
  esac
  shift
done

if [[ $CHECK_ONLY -eq 1 ]]; then
  python "$REPO/skills/reelforge-runner/scripts/preflight.py" || true
  exit 0
fi

if [[ ${#TARGETS[@]} -eq 0 && $WITH_WVP -eq 0 ]]; then
  usage
  exit 0
fi

copy_skill() {
  local name="$1" dest_root="$2"
  local src="$REPO/skills/$name"
  local dst="$dest_root/$name"
  if [[ ! -d "$src" ]]; then
    echo "  · 跳过 $name（仓库里没有这个 skill）"
    return 0
  fi
  mkdir -p "$dest_root"
  if [[ -e "$dst" ]]; then
    if [[ $FORCE -eq 1 ]]; then
      rm -rf "$dst"
      cp -R "$src" "$dst"
      echo "  ✓ $name → $dst（覆盖）"
    else
      local bak="$dst.bak-$(date +%Y%m%d-%H%M%S)"
      cp -R "$dst" "$bak"
      # 覆盖式更新：只写入仓库里的文件，保留 vendor / 本地配置
      cp -R "$src/." "$dst/"
      echo "  ✓ $name → $dst（备份 $bak）"
    fi
  else
    cp -R "$src" "$dst"
    echo "  ✓ $name → $dst"
  fi
}

# 配置：装到目标目录后，只生成 tts.yaml；人设由 personas_init.py 引导生成（不预设作者品牌）
ensure_config() {
  local root="$1"
  local cfg="$root/reelforge/config"
  [[ -d "$cfg" ]] || return 0
  if [[ -f "$cfg/tts.example.yaml" && ! -f "$cfg/tts.yaml" ]]; then
    cp "$cfg/tts.example.yaml" "$cfg/tts.yaml"
    echo "  生成配置 $cfg/tts.yaml"
  fi
}

install_for() {
  local t="$1"
  case "$t" in
    workbuddy)
      echo "WorkBuddy"
      copy_skill reelforge        "$UHOME/.workbuddy/skills"
      copy_skill reelforge-writer "$UHOME/.workbuddy/skills"
      copy_skill reelforge-runner "$UHOME/.workbuddy/skills"
      copy_skill reelforge-duo "$UHOME/.workbuddy/skills"
      ensure_config "$UHOME/.workbuddy/skills"
      ;;
    antigravity)
      echo "Antigravity"
      copy_skill reelforge-writer "$UHOME/.gemini/antigravity/skills"
      ;;
    dsh)
      echo "DeepSeek Harness"
      copy_skill reelforge-runner "$UHOME/.dsh/skills"
      copy_skill reelforge-duo "$UHOME/.dsh/skills"
      copy_skill reelforge "$UHOME/.dsh/skills"   # duo 依赖总控的脚本（state/similarity/pack_task）
      ;;
    claude)
      echo "Claude Code"
      copy_skill reelforge        "$UHOME/.claude/skills"
      copy_skill reelforge-writer "$UHOME/.claude/skills"
      copy_skill reelforge-runner "$UHOME/.claude/skills"
      copy_skill reelforge-duo "$UHOME/.claude/skills"
      ensure_config "$UHOME/.claude/skills"
      ;;
    codex)
      echo "Codex CLI"
      copy_skill reelforge        "$UHOME/.codex/skills"
      copy_skill reelforge-writer "$UHOME/.codex/skills"
      copy_skill reelforge-runner "$UHOME/.codex/skills"
      copy_skill reelforge-duo "$UHOME/.codex/skills"
      ensure_config "$UHOME/.codex/skills"
      ;;
  esac
}

for t in "${TARGETS[@]:-}"; do
  [[ -n "$t" ]] && install_for "$t"
done

# 可选：装 humanizer-zh（去 AI 味清洗，写稿第 ② 步用）
if [[ "$WITH_HUMANIZER" -eq 1 ]]; then
  for dest in "$UHOME/.workbuddy/skills" "$UHOME/.gemini/antigravity/skills" "$UHOME/.codex/skills"; do
    mkdir -p "$dest"
    if [[ -d "$dest/humanizer-zh" ]]; then
      echo "  · humanizer-zh 已存在：$dest/humanizer-zh"
    else
      git clone --depth 1 https://github.com/op7418/Humanizer-zh.git "$dest/humanizer-zh" >/dev/null 2>&1 \
        && echo "  ✓ humanizer-zh → $dest/humanizer-zh" \
        || echo "  ✗ humanizer-zh 安装失败（$dest）"
    fi
  done
fi


# wvp
if [[ $WITH_WVP -eq 1 ]]; then
  DEST="$REPO/skills/reelforge/vendor/web-video-presentation"
  if [[ -d "$DEST" ]]; then
    echo "wvp 已存在：$DEST"
  else
    echo "拉取 web-video-presentation…"
    mkdir -p "$(dirname "$DEST")"
    TMP="$(mktemp -d)"
    if git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/ConardLi/garden-skills "$TMP/repo" >/dev/null 2>&1; then
      ( cd "$TMP/repo" && git sparse-checkout set skills/web-video-presentation >/dev/null 2>&1 )
      cp -R "$TMP/repo/skills/web-video-presentation" "$DEST"
      rm -rf "$TMP"
      echo "  ✓ wvp → $DEST"
    else
      rm -rf "$TMP"
      echo "✗ git 克隆失败，改用 zip"
      curl -L -o "$TMP/garden.zip" https://codeload.github.com/ConardLi/garden-skills/zip/refs/heads/main
      unzip -q "$TMP/garden.zip" -d "$TMP/x"
      cp -R "$TMP/x/garden-skills-main/skills/web-video-presentation" "$DEST"
      rm -rf "$TMP"
      echo "  ✓ wvp（zip）→ $DEST"
    fi
  fi
fi

# 自检：preflight（缺什么、怎么补，一次说清）
if command -v python >/dev/null 2>&1 && [[ -f "$REPO/skills/reelforge-runner/scripts/preflight.py" ]]; then
  echo
  echo "依赖体检："
  python "$REPO/skills/reelforge-runner/scripts/preflight.py" || true
fi

cat <<EOF

完成。下一步：
  1) 建人设：python "$REPO/skills/reelforge/scripts/personas_init.py"
  2) （可选）改配音：$CFG/tts.yaml
  3) 起第一条：
     python "$REPO/skills/reelforge/scripts/state.py" init --work work/demo
     python "$REPO/skills/reelforge/scripts/pack_task.py" writer --work work/demo
  4) 换 agent / 接 MCP：看 DEPLOY.md
EOF
