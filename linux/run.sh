#!/usr/bin/env bash
# Launch the RE2 Outfit Converter GUI (same app as Windows).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/main.py" ]]; then
  echo "ERROR: main.py not found. Run this from the extracted package folder."
  exit 1
fi

chmod +x "$ROOT/setup.sh" "$ROOT/convert.sh" "$ROOT/run.sh" "$ROOT/menu.sh" 2>/dev/null || true

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo
  echo "First run: setting up Python environment (needs internet once)..."
  echo
  bash "$ROOT/setup.sh"
fi

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "ERROR: No graphical display (DISPLAY / WAYLAND_DISPLAY unset)."
  echo "The GUI needs a desktop session (or Steam Deck Desktop Mode)."
  echo "Use the CLI instead:"
  echo "  ./convert.sh list-outfits"
  echo "  ./convert.sh convert ./MyMod.zip --from elza --to noir -o ./out"
  echo "  ./menu.sh"
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
exec python main.py
