#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then python -m venv .venv; fi
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
skillhub configure --hub "$ROOT"
skillhub validate
echo "SkillHub ready. The current shell is activated."
echo "Future shells: source $ROOT/.venv/bin/activate"
echo "Play Store UI: skillhub marketplace --open"
