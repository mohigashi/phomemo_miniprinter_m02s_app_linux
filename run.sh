#!/usr/bin/env bash
# Phomemo M02S GUI launcher.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
source venv/bin/activate
export PYTHONPATH="$DIR:${PYTHONPATH:-}"
exec python -m phomemo_gui.app "$@"
