#!/usr/bin/env bash
# One-time setup for the Phomemo M02S GUI.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d venv ]; then
    echo "Creating venv..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install pillow pyserial

# phomemo_m02s library sits next door; add to path at runtime via run.sh

echo
echo "Setup complete. Run with: $DIR/run.sh"
