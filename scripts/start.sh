#!/usr/bin/env bash

# Runner script for cPanel Monitor Telegram Bot
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -d "venv" ]; then
    echo "[!] Virtual environment belum ditemukan. Menjalankan setup otomatis..."
    bash "$SCRIPT_DIR/setup.sh"
fi

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Execute bot using venv python
exec "$PROJECT_ROOT/venv/bin/python" "$PROJECT_ROOT/src/bot.py" "$@"
