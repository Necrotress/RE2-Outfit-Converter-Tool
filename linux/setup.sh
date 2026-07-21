#!/usr/bin/env bash
# One-time setup for Linux CLI (creates .venv).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found."
  echo "Steam Deck (Desktop Mode): open Discover or run:"
  echo "  sudo pacman -S python python-pip"
  exit 1
fi

echo "Creating virtual environment in .venv ..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-cli.txt

echo
echo "Setup complete."
echo "Convert a mod:"
echo "  ./convert.sh convert ./MyMod.zip --from elza --to noir -o ./out"
echo
echo "List outfit keys:"
echo "  ./convert.sh list-outfits"
echo
echo "Prefer .zip inputs. For .rar/.7z install p7zip so '7z' is on PATH."
