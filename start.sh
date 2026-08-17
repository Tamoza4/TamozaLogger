#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "venv/bin/python3" ]; then
    echo "[ERROR] Virtual environment not found. Please run ./install.sh first."
    exit 1
fi

echo "==============================================================================="
echo "                          STARTING TAMOZA LOGGER                               "
echo "==============================================================================="
exec ./venv/bin/python3 bot.py
