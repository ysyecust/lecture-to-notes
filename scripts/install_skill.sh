#!/usr/bin/env bash
# Install the lecture-to-notes skill (SKILL.md, references, agents, template, and every
# helper script) into one or more skill roots.
#
#   scripts/install_skill.sh                 # → ~/.agents/skills (DeepSeek Harness, Codex agents)
#   scripts/install_skill.sh --claude        # → ~/.claude/skills
#   scripts/install_skill.sh --codex         # → ~/.codex/skills
#   scripts/install_skill.sh --all           # all three
#   scripts/install_skill.sh /custom/root    # any directory that holds <name>/SKILL.md
#
# The installed layout is the one SKILL.md documents: helpers live flat under
# <root>/lecture-to-notes/assets/ next to notes-template.tex, and whisper_prompts/ is a
# subdirectory of assets/. Re-running replaces the previous copy.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_SRC="$REPO/skills/lecture-to-notes"
SCRIPTS="$REPO/scripts"
NAME="lecture-to-notes"

roots=()
for arg in "$@"; do
  case "$arg" in
    --agents) roots+=("$HOME/.agents/skills") ;;
    --claude) roots+=("$HOME/.claude/skills") ;;
    --codex)  roots+=("$HOME/.codex/skills") ;;
    --all)    roots+=("$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills") ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) roots+=("$arg") ;;
  esac
done
[ "${#roots[@]}" -eq 0 ] && roots=("$HOME/.agents/skills")

for root in "${roots[@]}"; do
  target="$root/$NAME"
  mkdir -p "$root"
  rm -rf "$target"
  cp -R "$SKILL_SRC" "$target"
  mkdir -p "$target/assets"
  cp "$SCRIPTS"/*.py "$target/assets/"
  cp "$SCRIPTS/prepare_cover.sh" "$target/assets/"
  cp -R "$SCRIPTS/whisper_prompts" "$target/assets/"
  find "$target" -name .DS_Store -delete
  sha="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  printf 'source=%s\ncommit=%s\ninstalled=%s\n' "$REPO" "$sha" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$target/assets/INSTALLED_FROM"
  count="$(find "$target/assets" -type f | wc -l | tr -d ' ')"
  echo "installed $NAME → $target ($count asset files, commit $sha)"
done
