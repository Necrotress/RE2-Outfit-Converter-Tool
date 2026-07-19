#!/usr/bin/env bash
# Easy menu for Steam Deck / Linux users (same engine as the Windows app).
# Keep this script next to setup.sh / convert.sh / re2_outfit_converter/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/convert.sh" ]]; then
  echo "ERROR: Could not find convert.sh next to this script."
  echo "Extract the full Linux package and run this from that folder."
  exit 1
fi

ensure_ready() {
  chmod +x "$ROOT/setup.sh" "$ROOT/convert.sh" \
    "$ROOT/RUN ON LINUX OR STEAM DECK.sh" 2>/dev/null || true
  if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo
    echo "First run: setting up a local Python environment (needs internet once)..."
    echo
    bash "$ROOT/setup.sh"
  fi
}

run_cli() {
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
  python -m re2_outfit_converter "$@"
}

pause() {
  echo
  read -r -p "Press Enter to continue..." _
}

pick_path() {
  local prompt="$1"
  local path=""
  echo
  read -r -p "$prompt" path
  # Trim quotes from drag-and-drop paths
  path="${path%\"}"
  path="${path#\"}"
  path="${path%\'}"
  path="${path#\'}"
  if [[ -z "$path" ]]; then
    echo "Cancelled (empty path)."
    return 1
  fi
  if [[ ! -e "$path" ]]; then
    echo "Not found: $path"
    return 1
  fi
  REPLY_PATH="$path"
  return 0
}

do_list() {
  echo
  run_cli list-outfits
  pause
}

do_analyze() {
  local mod
  if ! pick_path "Path to mod folder or .zip (drag-and-drop OK): "; then
    pause
    return 0
  fi
  mod="$REPLY_PATH"
  echo
  run_cli analyze "$mod" || true
  pause
}

do_convert() {
  local mod out from to name
  if ! pick_path "Path to mod folder or .zip (drag-and-drop OK): "; then
    pause
    return 0
  fi
  mod="$REPLY_PATH"
  echo
  echo "Outfit keys (use these for From / To):"
  run_cli list-outfits
  echo
  read -r -p "Convert FROM key (e.g. elza): " from
  read -r -p "Convert TO key   (e.g. noir): " to
  if [[ -z "$from" || -z "$to" ]]; then
    echo "Need both From and To keys."
    pause
    return 0
  fi
  read -r -p "Output folder [./out]: " out
  out="${out:-./out}"
  mkdir -p "$out"
  read -r -p "In-game outfit name (optional, Enter to skip): " name
  echo
  echo "Converting..."
  if [[ -n "$name" ]]; then
    run_cli convert "$mod" --from "$from" --to "$to" -o "$out" --name "$name"
  else
    run_cli convert "$mod" --from "$from" --to "$to" -o "$out"
  fi
  echo
  echo "Done. Check: $out"
  echo "Put the new .zip into Fluffy's RE2R Mods folder (do not extract)."
  pause
}

do_advanced() {
  echo
  echo "Type CLI arguments (same as convert.sh)."
  echo "Examples:"
  echo "  list-outfits"
  echo "  analyze ./MyMod.zip"
  echo "  convert ./MyMod.zip --from elza --to noir -o ./out"
  echo
  read -r -p "> " line
  if [[ -z "${line// }" ]]; then
    echo "Cancelled."
    pause
    return 0
  fi
  # shellcheck disable=SC2086
  echo
  run_cli $line || true
  pause
}

ensure_ready

while true; do
  clear 2>/dev/null || true
  cat <<EOF
========================================
 RE2 Outfit Converter
 Steam Deck / Linux
========================================

  Same conversion engine as the Windows app.
  Prefer .zip mods. Originals are never modified.

  1) List outfit keys
  2) Analyze a mod
  3) Convert a mod   (guided)
  4) Advanced command
  5) Quit

EOF
  read -r -p "Choose [1-5]: " choice
  case "${choice:-}" in
    1) do_list ;;
    2) do_analyze ;;
    3) do_convert ;;
    4) do_advanced ;;
    5|q|Q) echo "Bye."; exit 0 ;;
    *) echo "Unknown option."; pause ;;
  esac
done
