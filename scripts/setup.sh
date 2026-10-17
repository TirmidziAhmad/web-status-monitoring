#!/usr/bin/env bash

# Setup Script for cPanel Monitor Telegram Bot
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================================="
echo "  Setup cPanel Monitor Telegram Bot Environment"
echo "========================================================="

# 1. Check Python
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python 3 tidak ditemukan. Silakan pasang python3 terlebih dahulu."
    exit 1
fi

echo "[1/4] Menggunakan Python: $($PYTHON_BIN --version)"

# 2. Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "[2/4] Membuat virtual environment (venv)..."
    if command -v uv >/dev/null 2>&1; then
        uv venv venv
    else
        $PYTHON_BIN -m venv venv
    fi
else
    echo "[2/4] Virtual environment (venv) sudah ada."
fi

# 3. Install Requirements
echo "[3/4] Memasang dependensi dari requirements.txt..."
if command -v uv >/dev/null 2>&1; then
    uv pip install -r requirements.txt --python venv/bin/python
else
    venv/bin/pip install -r requirements.txt
fi

# 4. Initialize .env if missing
echo "[4/4] Memeriksa file konfigurasi .env..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  -> File .env berhasil dibuat dari template .env.example!"
    echo "  -> Silakan edit file .env untuk mengisi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID."
else
    echo "  -> File .env sudah ada."
fi

# Make scripts executable
chmod +x scripts/*.sh 2>/dev/null || true

echo ""
echo "========================================================="
echo "  SETUP BERHASIL!"
echo "========================================================="
echo "Langkah selanjutnya:"
echo "1. Buka file .env dan masukkan TELEGRAM_BOT_TOKEN dari @BotFather"
echo "2. Uji coba cek kesehatan server:"
echo "     ./scripts/start.sh --check-once"
echo "3. Jalankan bot di terminal:"
echo "     ./scripts/start.sh"
echo "4. Atau pasang sebagai background service 24/7 (systemd):"
echo "     ./scripts/manage_service.sh install"
echo "========================================================="
