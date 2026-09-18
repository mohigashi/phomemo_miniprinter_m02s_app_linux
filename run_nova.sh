#!/usr/bin/env bash
# Phomemo M02S GUI launcher for Nova (WSL) — tkinter is vendored under vendor/tk.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
source venv/bin/activate

export PYTHONPATH="$DIR/vendor/tk:$DIR":"${PYTHONPATH:-}"
export LD_LIBRARY_PATH="$DIR/vendor/tk/lib:${LD_LIBRARY_PATH:-}"

exec python -m phomemo_gui.app "$@"
