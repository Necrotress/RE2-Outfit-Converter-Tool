#!/usr/bin/env bash
# One-time setup: creates .venv and installs GUI + CLI dependencies.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.10+ (with venv), then retry."
  echo "  Debian/Ubuntu:  sudo apt install python3 python3-venv python3-pip python3-tk"
  echo "  Arch:           sudo pacman -S python python-pip tk"
  exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "ERROR: Python Tkinter is not available (needed for the GUI)."
  echo "  Debian/Ubuntu:  sudo apt install python3-tk"
  echo "  Arch:           sudo pacman -S tk"
  echo "  Fedora:         sudo dnf install python3-tkinter"
  echo
  echo "Then re-run ./setup.sh (or ./run.sh)."
  exit 1
fi

if [[ ! -f "$ROOT/requirements-linux.txt" ]]; then
  echo "ERROR: requirements-linux.txt not found. Run this from the extracted package folder."
  exit 1
fi

if [[ ! -f "$ROOT/main.py" ]]; then
  echo "ERROR: main.py not found. Run this from the extracted package folder."
  exit 1
fi

echo "Creating virtual environment in .venv ..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-linux.txt

echo
echo "Setup complete. Run ./run.sh for the GUI, or:"
echo "  ./convert.sh convert ./MyMod.zip --from elza --to noir -o ./out"
echo "  ./menu.sh          # text menu (no GUI)"
echo
echo "Prefer .zip inputs. For .rar/.7z install p7zip so '7z' is on PATH."
