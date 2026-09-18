#!/usr/bin/env bash
# Phomemo M02S GUI launcher (Evo / native Linux).
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
source venv/bin/activate

# tkinter is vendored under vendor/tk (Bluetooth-capable syspython 3.12
# lacks system tkinter, and the uv-clang 3.11 build lacks AF_BLUETOOTH).
export PYTHONPATH="$DIR/vendor/tk:$DIR:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="$DIR/vendor/tk/lib:${LD_LIBRARY_PATH:-}"

exec python -m phomemo_gui.app "$@"
