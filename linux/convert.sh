#!/usr/bin/env bash
# Run the RE2 Outfit Converter CLI (auto-setup on first run).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "First run: setting up Python environment..."
  bash ./setup.sh
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python -m re2_outfit_converter "$@"
